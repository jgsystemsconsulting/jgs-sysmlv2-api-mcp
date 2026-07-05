# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
from dataclasses import dataclass
import os
from urllib.parse import urlparse
from .transport import validate_loopback_or_https   # module-level so tests can patch it

class ConfigError(Exception):
    pass

@dataclass(frozen=True)
class Config:
    base_url: str
    token: str
    project: str
    branch: str | None
    page_size: int = 50
    buffer_cap: int = 5000
    token_ttl_seconds: float = 120.0
    connect_timeout: float = 5.0
    read_timeout: float = 30.0

def load_config() -> Config:
    base_url = os.environ.get("SYSMLV2_BASE_URL")
    token = os.environ.get("SYSMLV2_TOKEN")
    project = os.environ.get("SYSMLV2_PROJECT")
    if not base_url:
        raise ConfigError("SYSMLV2_BASE_URL is required")
    if not token:
        raise ConfigError("SYSMLV2_TOKEN is required (env var only; never in .mcp.json)")
    if not project:
        raise ConfigError("SYSMLV2_PROJECT is required")
    # SC9: reject non-HTTPS / non-loopback BEFORE any network use. Delegates to the
    # transport validator (Task 3, imported at module top so tests can patch it),
    # which resolves the host and requires EVERY resolved IP to be loopback for the
    # http:// exception — closing decimal-IP / link-local / DNS bypasses.
    try:
        validate_loopback_or_https(base_url)
    except ValueError as e:
        raise ConfigError(f"invalid base URL (HTTPS/loopback rule): {e}") from e
    return Config(
        base_url=base_url, token=token, project=project,
        branch=os.environ.get("SYSMLV2_BRANCH"),
        page_size=int(os.environ.get("SYSMLV2_PAGE_SIZE", "50")),
    )
