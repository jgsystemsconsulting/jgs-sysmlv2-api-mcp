# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
import pytest
from jgs_sysmlv2_api_mcp.transport import (
    validate_loopback_or_https, sanitize_endpoint, redact,
)

def test_link_local_metadata_rejected():
    # 169.254.169.254 must never be reachable via the http-localhost exception
    with pytest.raises(ValueError, match="loopback"):
        validate_loopback_or_https("http://169.254.169.254/latest/meta-data")

def test_decimal_ip_loopback_bypass_rejected():
    # 2852039166 == 169.254.169.254 (link-local metadata IP), decimal-encoded.
    # A decimal-encoded host must resolve+validate the same as its dotted form,
    # not be string-matched — this decimal maps outside loopback, so it must
    # still be rejected. (2130706433 would decode to 127.0.0.1, which IS
    # loopback and would correctly be ACCEPTED — not usable for this test.)
    with pytest.raises(ValueError):
        validate_loopback_or_https("http://2852039166/")

def test_https_any_host_ok():
    validate_loopback_or_https("https://api.example.com")  # no raise

def test_sanitize_strips_userinfo_and_query():
    assert sanitize_endpoint("https://user:pw@h.com/x?token=abc") == "https://h.com/x"

def test_redact_hides_token():
    assert "SECRET" not in redact("Authorization: Bearer SECRET", secrets=["SECRET"])
