"""
Consul client wrapper for service discovery and registration.
Uses Consul as the authoritative name server for internal services (*.service.consul).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any
from urllib.parse import urlparse, urlunparse

import consul

logger = logging.getLogger(__name__)

# Hostnames that should be resolved via Consul (authoritative name server)
CONSUL_SERVICE_DOMAIN = ".service.consul"
CONSUL_SERVICE_PATTERN = re.compile(
    r"^([a-zA-Z0-9_-]+)" + re.escape(CONSUL_SERVICE_DOMAIN) + r"$"
)


class ConsulClient:
    """
    Consul client for service discovery and registration.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8500,
        token: str | None = None,
    ) -> None:
        """
        Args:
            host: Consul server host
            port: Consul server port
            token: Optional ACL token
        """
        self._host = host
        self._port = port
        # python-consul reads CONSUL_HTTP_ADDR at init and expects <host>:<port> (no http://).
        # If set to http://host:port it raises. Unset so the library uses our host/port.
        # Do not restore: later requests use the client's stored host/port.
        old_consul_addr = os.environ.pop("CONSUL_HTTP_ADDR", None)
        try:
            self._client = consul.Consul(host=host, port=port, token=token)
        finally:
            # Leave unset so python-consul never sees invalid format on any code path
            if old_consul_addr:
                pass  # deliberately not restored

    def register_service(
        self,
        service_name: str,
        service_id: str,
        address: str,
        port: int,
        health_check_url: str | None = None,
        tags: list[str] | None = None,
        meta: dict[str, str] | None = None,
    ) -> None:
        """
        Register a service with Consul.

        Args:
            service_name: Service name (e.g., "speech")
            service_id: Unique service instance ID
            address: Service address
            port: Service port
            health_check_url: Optional health check URL (default: http://address:port/health)
            tags: Optional service tags
            meta: Optional service metadata
        """
        if health_check_url is None:
            health_check_url = f"http://{address}:{port}/health"

        check = consul.Check.http(
            url=health_check_url,
            interval="10s",
            timeout="3s",
            deregister="30s",
        )

        try:
            # python-consul does not support 'meta' parameter; omit it
            self._client.agent.service.register(
                name=service_name,
                service_id=service_id,
                address=address,
                port=port,
                check=check,
                tags=tags or [],
            )
            logger.info(
                "Registered service %s (ID: %s) at %s:%d",
                service_name,
                service_id,
                address,
                port,
            )
        except Exception as e:
            logger.exception("Failed to register service with Consul: %s", e)
            raise

    def deregister_service(self, service_id: str) -> None:
        """
        Deregister a service from Consul.

        Args:
            service_id: Service instance ID
        """
        try:
            self._client.agent.service.deregister(service_id)
            logger.info("Deregistered service %s", service_id)
        except Exception as e:
            logger.warning("Failed to deregister service from Consul: %s", e)

    def get_healthy_services(
        self,
        service_name: str,
        tag: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get healthy service instances.

        Args:
            service_name: Service name
            tag: Optional service tag filter

        Returns:
            List of service instances with 'Address' and 'ServicePort'
        """
        try:
            _, services = self._client.health.service(
                service=service_name,
                tag=tag,
                passing=True,  # Only healthy services
            )
            result = []
            for service in services:
                service_info = service.get("Service", {})
                result.append(
                    {
                        "address": service_info.get("Address", ""),
                        "port": service_info.get("Port", 0),
                        "id": service_info.get("ID", ""),
                        "tags": service_info.get("Tags", []),
                        "meta": service_info.get("Meta", {}),
                    }
                )
            return result
        except Exception as e:
            logger.warning("Failed to get healthy services from Consul: %s", e)
            return []

    def get_service_urls(
        self,
        service_name: str,
        tag: str | None = None,
        protocol: str = "http",
    ) -> list[str]:
        """
        Get healthy service URLs.

        Args:
            service_name: Service name
            tag: Optional service tag filter
            protocol: URL protocol (http or https)

        Returns:
            List of service URLs
        """
        services = self.get_healthy_services(service_name, tag)
        return [f"{protocol}://{s['address']}:{s['port']}" for s in services]

    def set_key(self, key: str, value: str) -> bool:
        """
        Set a key-value pair in Consul KV store.

        Args:
            key: Key name
            value: Value string

        Returns:
            True if successful
        """
        try:
            return self._client.kv.put(key, value)
        except Exception as e:
            logger.warning("Failed to set Consul key %s: %s", key, e)
            return False

    def get_key(self, key: str) -> str | None:
        """
        Get a value from Consul KV store.

        Args:
            key: Key name

        Returns:
            Value string or None
        """
        try:
            _, data = self._client.kv.get(key)
            if data:
                return data.get("Value", b"").decode("utf-8")
            return None
        except Exception as e:
            logger.warning("Failed to get Consul key %s: %s", key, e)
            return None

    def resolve_consul_url(self, url: str) -> str:
        """
        If the URL host is *.service.consul, resolve it via Consul (authoritative
        name server) and return a URL with the resolved address. Otherwise return
        the URL unchanged.

        Args:
            url: URL that may contain a host like ollama.service.consul

        Returns:
            URL with host replaced by Consul-resolved address, or original URL
        """
        try:
            parsed = urlparse(url)
            host = (parsed.hostname or "").strip().lower()
            if not host or not host.endswith(CONSUL_SERVICE_DOMAIN):
                return url
            match = CONSUL_SERVICE_PATTERN.match(host)
            if not match:
                return url
            service_name = match.group(1)
            services = self.get_healthy_services(service_name)
            if not services:
                logger.warning(
                    "Consul: no healthy instances for %s, using URL as-is", service_name
                )
                return url
            first = services[0]
            address = first.get("address", "").strip()
            port = first.get("port") or (parsed.port if parsed.port is not None else 0)
            if not address:
                return url
            # Rebuild URL with resolved host:port
            netloc = f"{address}:{port}" if port else address
            new_parsed = parsed._replace(netloc=netloc)
            resolved = urlunparse(new_parsed)
            logger.debug(
                "Consul: resolved %s -> %s", url, resolved
            )
            return resolved
        except Exception as e:
            logger.debug("Consul: resolve %s failed: %s", url, e)
            return url


def resolve_url_via_consul(
    url: str,
    consul_host: str = "localhost",
    consul_port: int = 8500,
) -> str:
    """
    Resolve a URL whose host is *.service.consul via Consul (authoritative name
    server). If the host is not a Consul service name, return the URL unchanged.

    Args:
        url: URL that may contain a host like ollama.service.consul:11434
        consul_host: Consul server host
        consul_port: Consul server port

    Returns:
        URL with host replaced by Consul-resolved address, or original URL
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").strip().lower()
    if not host or not host.endswith(CONSUL_SERVICE_DOMAIN):
        return url
    try:
        client = ConsulClient(host=consul_host, port=consul_port)
        return client.resolve_consul_url(url)
    except Exception as e:
        logger.debug("resolve_url_via_consul failed: %s", e)
        return url
