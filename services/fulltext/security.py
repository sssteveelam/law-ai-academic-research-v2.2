from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeURL(ValueError):
    """URL is not safe for an outbound full-text request."""


def _is_public_ip(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_global
    except ValueError:
        return False


def validate_public_http_url(value: str) -> str:
    """Validate syntactic URL safety (no credentials, local IPs or odd ports)."""
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError as exc:
        raise UnsafeURL("invalid URL or port") from exc
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeURL("only http and https URLs are allowed")
    if parsed.username or parsed.password:
        raise UnsafeURL("URLs with embedded credentials are not allowed")
    if port is not None and port not in {80, 443}:
        raise UnsafeURL("only standard HTTP(S) ports are allowed")
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if not hostname or hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".localhost"):
        raise UnsafeURL("localhost is not an allowed download host")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise UnsafeURL("private or special IP addresses are not allowed")
    return value


def validate_public_dns_host(value: str) -> None:
    """Reject hosts whose DNS returns ANY non-public IP before a request is made.

    DNS rebinding between this check and connect remains a transport-level risk;
    production deployments should additionally block private egress at network level.
    """
    hostname = urlparse(validate_public_http_url(value)).hostname
    assert hostname is not None
    try:
        ipaddress.ip_address(hostname)
        return  # Literal IP has already passed the syntax/public-address validation.
    except ValueError:
        pass
    try:
        answers = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise UnsafeURL("unable to resolve download host") from exc
    if not answers or any(not _is_public_ip(item[4][0]) for item in answers):
        raise UnsafeURL("download host resolves to a private or special IP")
