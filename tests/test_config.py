# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
import os
import pytest
from jgs_sysmlv2_api_mcp.config import load_config, ConfigError

def test_missing_token_fails_fast(monkeypatch):
    monkeypatch.setenv("SYSMLV2_BASE_URL", "https://api.example.com")
    monkeypatch.delenv("SYSMLV2_TOKEN", raising=False)
    with pytest.raises(ConfigError, match="SYSMLV2_TOKEN"):
        load_config()

def test_http_non_loopback_rejected(monkeypatch):
    # startup rejects a non-loopback http:// endpoint BEFORE any network call (SC9).
    # Mock the transport validator so the test is DNS-independent and deterministic.
    monkeypatch.setenv("SYSMLV2_BASE_URL", "http://api.example.com")
    monkeypatch.setenv("SYSMLV2_TOKEN", "t")
    monkeypatch.setenv("SYSMLV2_PROJECT", "p")
    import jgs_sysmlv2_api_mcp.config as cfgmod
    def _reject(url): raise ValueError("http:// allowed only for loopback")
    monkeypatch.setattr(cfgmod, "validate_loopback_or_https", _reject, raising=False)
    with pytest.raises(ConfigError, match="loopback"):
        load_config()

def test_metadata_endpoint_rejected(monkeypatch):
    # SC9 SSRF: the cloud metadata IP must be rejected at startup.
    monkeypatch.setenv("SYSMLV2_BASE_URL", "http://169.254.169.254/latest/meta-data")
    monkeypatch.setenv("SYSMLV2_TOKEN", "t")
    monkeypatch.setenv("SYSMLV2_PROJECT", "p")
    with pytest.raises(ConfigError):
        load_config()   # real validator resolves 169.254.169.254 -> link-local -> reject

def test_http_localhost_allowed(monkeypatch):
    monkeypatch.setenv("SYSMLV2_BASE_URL", "http://localhost:9000")
    monkeypatch.setenv("SYSMLV2_TOKEN", "t")
    monkeypatch.setenv("SYSMLV2_PROJECT", "p")
    cfg = load_config()   # localhost resolves to loopback -> allowed
    assert cfg.base_url == "http://localhost:9000"
    assert cfg.project == "p"
