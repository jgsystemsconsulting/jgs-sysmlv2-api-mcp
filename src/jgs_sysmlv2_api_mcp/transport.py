# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
import ipaddress
import socket
from urllib.parse import urlparse, urlunparse

_LOOPBACK_NETS = [ipaddress.ip_network("127.0.0.0/8"), ipaddress.ip_network("::1/128")]


def _all_resolved_ips(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None)
    return [i[4][0] for i in infos]


def _is_loopback(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return any(addr in net for net in _LOOPBACK_NETS)


def validate_loopback_or_https(base_url: str) -> None:
    """https any host; http only if EVERY resolved A/AAAA is loopback."""
    p = urlparse(base_url)
    if p.scheme == "https":
        return
    if p.scheme != "http":
        raise ValueError("scheme must be http or https")
    host = p.hostname or ""
    try:
        ips = _all_resolved_ips(host)
    except socket.gaierror as exc:
        raise ValueError(f"http:// host {host!r} could not be resolved: {exc}") from exc
    if not ips or not all(_is_loopback(ip) for ip in ips):
        raise ValueError(f"http:// allowed only for loopback; {host} resolved to {ips}")


def pinned_ip(base_url: str) -> str | None:
    """Resolve once; return the loopback IP to connect to (None for https/remote)."""
    p = urlparse(base_url)
    if p.scheme == "https":
        return None
    return _all_resolved_ips(p.hostname or "")[0]


def sanitize_endpoint(url: str) -> str:
    p = urlparse(url)
    netloc = p.hostname or ""
    if p.port:
        netloc += f":{p.port}"
    return urlunparse((p.scheme, netloc, p.path, "", "", ""))


def redact(text: str, secrets: list[str]) -> str:
    out = text
    for s in secrets:
        if s:
            out = out.replace(s, "***REDACTED***")
    return out
