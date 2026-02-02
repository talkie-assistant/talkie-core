#!/usr/bin/env python3
"""
CLI launcher for module servers. Module list is derived from discovery;
default ports come from config (modules.<name>.server.port) or fallback map.
Usage:
    python run_module_server.py speech --port 8001
    python run_module_server.py rag --port 8002
    python run_module_server.py browser --port 8003
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

# Ensure project root is on path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Fallback ports when config is not available
DEFAULT_PORTS = {
    "speech": 8001,
    "rag": 8002,
    "browser": 8003,
}


def _discovered_module_names() -> list[str]:
    """Return list of discovered module directory names (for server choices)."""
    try:
        from modules.discovery import discover_modules

        discovered = discover_modules(_ROOT / "modules")
        return [config_path.parent.name for _name, config_path in discovered]
    except Exception:
        return list(DEFAULT_PORTS.keys())


def _default_port(module_name: str) -> int:
    """Return default port for module (from config or DEFAULT_PORTS)."""
    try:
        from config import load_config

        cfg = load_config()
        port = (
            cfg.get("modules", {})
            .get(module_name, {})
            .get("server", {})
            .get("port")
        )
        if port is not None:
            return int(port)
    except Exception:
        pass
    return DEFAULT_PORTS.get(module_name, 8000)


def main() -> None:
    """Main entry point."""
    choices = _discovered_module_names()
    parser = argparse.ArgumentParser(description="Launch a Talkie module server")
    parser.add_argument(
        "module",
        choices=choices,
        help="Module to launch (discovered: %s)" % ", ".join(choices),
    )
    parser.add_argument("--host", default="localhost", help="Host to bind to")
    parser.add_argument(
        "--port", type=int, help="Port to bind to (default: from config or module default)"
    )
    parser.add_argument("--api-key", help="Optional API key for authentication")
    args = parser.parse_args()

    port = args.port if args.port is not None else _default_port(args.module)

    # Dynamic import: modules.<name>.server must define main()
    try:
        server_mod = importlib.import_module("modules.%s.server" % args.module)
        server_main = getattr(server_mod, "main", None)
        if server_main is None:
            print("Module %s has no server.main()" % args.module, file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print("Failed to load module server %s: %s" % (args.module, e), file=sys.stderr)
        sys.exit(1)

    sys.argv = [
        "modules.%s.server" % args.module,
        "--host",
        args.host,
        "--port",
        str(port),
    ]
    if args.api_key:
        sys.argv.extend(["--api-key", args.api_key])
    server_main()


if __name__ == "__main__":
    main()
