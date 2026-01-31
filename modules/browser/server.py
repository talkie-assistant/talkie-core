"""
Browser module HTTP server.
Exposes browser operations via REST API.
"""

from __future__ import annotations

import argparse
import logging
from typing import Any, Callable

from fastapi import Request, status

from modules.api.server import BaseModuleServer
from modules.browser.service import BrowserService

logger = logging.getLogger(__name__)


class BrowserModuleServer(BaseModuleServer):
    """HTTP server for browser module."""

    def __init__(
        self,
        config: dict[str, Any],
        ollama_client: Any = None,
        rag_ingest_callback: Callable[[str, str], None] | None = None,
        host: str = "localhost",
        port: int = 8003,
        api_key: str | None = None,
    ) -> None:
        super().__init__(
            module_name="browser",
            module_version="1.0.0",
            host=host,
            port=port,
            api_key=api_key,
        )
        self._config = config
        self._ollama_client = ollama_client
        self._rag_ingest_callback = rag_ingest_callback
        self._service: BrowserService | None = None
        self._setup_endpoints()

    def _setup_endpoints(self) -> None:
        """Set up browser-specific endpoints."""

        @self._app.post("/execute")
        async def execute(request: Request) -> dict[str, Any]:
            """Execute browser intent."""
            try:
                if r := self._require_service(self._service):
                    return r
                data = await request.json()

                # Support both "utterance" (for full processing) and "intent" (for pre-parsed)
                if "utterance" in data:
                    # Full utterance - parse intent first (requires LLM)
                    if self._ollama_client is None:
                        return self._error_response(
                            status.HTTP_400_BAD_REQUEST,
                            "invalid_request",
                            "LLM client required for utterance parsing",
                        )
                    from llm.prompts import (
                        build_browse_intent_prompts,
                        parse_browse_intent,
                    )

                    utterance = data.get("utterance", "")
                    browse_system, browse_user = build_browse_intent_prompts(utterance)
                    raw = self._ollama_client.generate(browse_user, browse_system)
                    intent = parse_browse_intent(raw)
                elif "intent" in data:
                    # Pre-parsed intent
                    intent = data.get("intent", {})
                else:
                    return self._error_response(
                        status.HTTP_400_BAD_REQUEST,
                        "invalid_request",
                        "utterance or intent required",
                    )

                result = self._service.execute(
                    intent,
                    rag_ingest=self._rag_ingest_callback,
                    open_locally=False,
                )
                if isinstance(result, tuple):
                    msg, open_url = result
                    return {"result": msg, "open_url": open_url}
                return {"result": result}
            except Exception as e:
                logger.exception("Browser execute failed: %s", e)
                return self._error_response(
                    status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", str(e)
                )

    async def startup(self) -> None:
        """Initialize browser service on startup."""
        await super().startup()
        try:
            from sdk.config import get_browser_section

            browser_config = get_browser_section(self._config)
            if not browser_config.get("enabled", False):
                logger.warning("Browser module disabled in config")
                self.set_ready(False)
                return
            self._service = BrowserService(browser_config)
            self.set_ready(True)
            logger.info("Browser module initialized and ready")
        except Exception as e:
            logger.exception("Failed to initialize browser module: %s", e)
            self.set_ready(False)

    async def shutdown(self) -> None:
        """Cleanup on shutdown."""
        await super().shutdown()

    def get_config_dict(self) -> dict[str, Any]:
        """Get current configuration."""
        return self._config

    def update_config_dict(self, config: dict[str, Any]) -> None:
        """Update configuration."""
        self._config.update(config)
        # Recreate service
        try:
            from sdk.config import get_browser_section

            browser_config = get_browser_section(self._config)
            self._service = BrowserService(browser_config)
        except Exception as e:
            logger.exception("Failed to update browser config: %s", e)

    def reload_config_from_file(self) -> None:
        """Reload configuration from file; base loads config, we apply via update_config_dict."""
        try:
            super().reload_config_from_file()
        except Exception as e:
            logger.exception("Failed to reload browser config from file: %s", e)
            raise


def main() -> None:
    """CLI entry point for browser module server."""
    parser = argparse.ArgumentParser(description="Browser module HTTP server")
    parser.add_argument("--host", default="localhost", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8003, help="Port to bind to")
    parser.add_argument("--api-key", help="Optional API key for authentication")
    args = parser.parse_args()

    # Load config
    from config import load_config, resolve_internal_service_url

    config = load_config()
    consul_cfg = (config.get("infrastructure") or {}).get("consul") or {}

    # Create Ollama client for intent parsing (resolve via Consul if *.service.consul)
    ollama_cfg = config.get("ollama", {})
    base_url = resolve_internal_service_url(
        ollama_cfg.get("base_url", "http://localhost:11434"), consul_cfg
    )
    from llm.client import OllamaClient

    ollama_client = OllamaClient(
        base_url=base_url,
        model_name=ollama_cfg.get("model_name", "mistral"),
        options=ollama_cfg.get("options"),
    )

    # Create and run server
    server = BrowserModuleServer(
        config=config,
        ollama_client=ollama_client,
        host=args.host,
        port=args.port,
        api_key=args.api_key,
    )
    server.run()


if __name__ == "__main__":
    main()
