# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""Unit tests for the Ed25519 licence verifier (src/.../licence.py).

Self-contained: generates its own test Ed25519 keypair(s) and mints licence
bytes in the exact byte format the production mint tool produces
(``cameo-sysmlv2-mcp/licensing/sign_licence.py``: LF-only, ``# jgsc-<product>
licence file`` header, ``key=value`` lines, ``signature=`` last). No real
production key is used anywhere; every fixture is minted with a locally
generated test key and verified against that same key via the pubkey seam.

Each fixture asserts the EXACT reason code, not just a boolean.
"""
from __future__ import annotations

import base64
from datetime import date, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from jgs_sysmlv2_api_mcp import licence
from jgs_sysmlv2_api_mcp.licence import (
    LICENCE_FILENAME,
    PRODUCT,
    LicenceResult,
    find_licence_path,
    load_licence,
    verify_licence_bytes,
)

# Field ordering that the real mint tool (sign_licence.py REQUIRED_FIELDS) uses.
# The verifier does not depend on order, but mirroring it proves byte-format
# compatibility with the production tool.
MINT_FIELD_ORDER = [
    "version",
    "product",
    "tier",
    "customer",
    "contact",
    "seats",
    "issued",
    "expires",
    "features",
    "scriptkey",
]

REF_DATE = date(2026, 7, 4)  # fixed reference date -> clock-independent tests


# --- Test key + minting helpers ----------------------------------------------


def _make_key() -> tuple[Ed25519PrivateKey, str]:
    """Return (private_key, public_key_b64) for a fresh test keypair."""
    priv = Ed25519PrivateKey.generate()
    raw_pub = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return priv, base64.b64encode(raw_pub).decode("ascii")


def _build_payload(fields: dict, product: str) -> bytes:
    """Mirror sign_licence.py build_payload(): header + ordered key=value lines.

    Only keys present in ``fields`` are emitted, in MINT_FIELD_ORDER, then any
    remaining (unknown/extra) keys in insertion order. Terminated with a final
    ``\\n``. LF-only.
    """
    lines = [f"# jgsc-{product} licence file"]
    emitted = set()
    for key in MINT_FIELD_ORDER:
        if key in fields:
            lines.append(f"{key}={fields[key]}")
            emitted.add(key)
    for key, value in fields.items():
        if key not in emitted:
            lines.append(f"{key}={value}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _sign(priv: Ed25519PrivateKey, payload: bytes) -> str:
    return base64.b64encode(priv.sign(payload)).decode("ascii")


def _mint(priv: Ed25519PrivateKey, fields: dict, product: str | None = None) -> bytes:
    """Produce the full signed licence file bytes (payload + signature line)."""
    product = product if product is not None else fields.get("product", PRODUCT)
    payload = _build_payload(fields, product)
    sig = _sign(priv, payload)
    return payload + f"signature={sig}\n".encode("utf-8")


def _default_fields(**overrides) -> dict:
    """A complete, valid set of licence fields; override any via kwargs."""
    fields = {
        "version": "1",
        "product": PRODUCT,
        "tier": "pro",
        "customer": "Acme Systems Ltd.",
        "contact": "eng@acme.example",
        "seats": "5",
        "issued": "2026-01-01",
        "expires": "2027-01-01",
        "features": "write,diagrams,airgap",
        "scriptkey": "ZHVtbXktc2NyaXB0LWtleQ==",
    }
    fields.update(overrides)
    return fields


@pytest.fixture()
def key():
    priv, pub_b64 = _make_key()
    return priv, pub_b64


def _verify(raw: bytes, pub_b64: str, ref: date = REF_DATE, **kw) -> LicenceResult:
    return verify_licence_bytes(
        raw, public_key_b64=pub_b64, reference_date=ref, **kw
    )


# --- Happy path --------------------------------------------------------------


def test_valid_pro(key):
    priv, pub = key
    raw = _mint(priv, _default_fields())
    r = _verify(raw, pub)
    assert r.valid is True
    assert r.reason == "ok"
    assert r.tier == "pro"
    assert r.customer == "Acme Systems Ltd."
    assert r.expires == "2027-01-01"
    assert r.seats == "5"
    assert r.features == "write,diagrams,airgap"


def test_valid_on_expiry_date_exactly(key):
    priv, pub = key
    raw = _mint(priv, _default_fields(expires=REF_DATE.isoformat()))
    r = _verify(raw, pub)
    assert r.valid is True
    assert r.reason == "ok"
    assert r.days_remaining == 0


def test_expired_day_after(key):
    priv, pub = key
    yesterday = (REF_DATE - timedelta(days=1)).isoformat()
    raw = _mint(priv, _default_fields(expires=yesterday))
    r = _verify(raw, pub)
    assert r.valid is False
    assert r.reason == "expired"


# --- Signature integrity -----------------------------------------------------


def test_tampered_signature(key):
    priv, pub = key
    raw = _mint(priv, _default_fields())
    # Flip a byte in the payload after signing -> signature no longer matches.
    tampered = bytearray(raw)
    # Find "tier=pro" and mutate a character in the value region.
    idx = raw.index(b"tier=pro")
    tampered[idx + 5] = tampered[idx + 5] ^ 0x01
    r = _verify(bytes(tampered), pub)
    assert r.valid is False
    assert r.reason == "bad_signature"


def test_valid_signature_from_wrong_key(key):
    priv, pub = key
    other_priv, _ = _make_key()
    # Signed correctly by `other_priv`, product string correct, but verified
    # against `pub` (the first key). Signature check precedes product check.
    raw = _mint(other_priv, _default_fields())
    r = _verify(raw, pub)
    assert r.valid is False
    assert r.reason == "bad_signature"


# --- Field-level rejections --------------------------------------------------


def test_wrong_product(key):
    priv, pub = key
    fields = _default_fields(product="some-other-product")
    # Sign with the header matching the wrong product so the payload is
    # self-consistent and the signature is valid; only the product FIELD is wrong.
    raw = _mint(priv, fields, product="some-other-product")
    r = _verify(raw, pub)
    assert r.valid is False
    assert r.reason == "wrong_product"


def test_missing_required_field(key):
    priv, pub = key
    fields = _default_fields()
    del fields["tier"]
    raw = _mint(priv, fields)
    r = _verify(raw, pub)
    assert r.valid is False
    assert r.reason == "missing"


def test_unsupported_version(key):
    priv, pub = key
    raw = _mint(priv, _default_fields(version="2"))
    r = _verify(raw, pub)
    assert r.valid is False
    assert r.reason == "unsupported_version"


# --- Line-ending normalization -----------------------------------------------


def test_crlf_normalizes_to_valid(key):
    priv, pub = key
    raw = _mint(priv, _default_fields())  # LF-only, correctly signed
    crlf = raw.replace(b"\n", b"\r\n")
    r = _verify(crlf, pub)
    assert r.valid is True
    assert r.reason == "ok"


def test_mixed_line_endings_normalize_to_valid(key):
    priv, pub = key
    raw = _mint(priv, _default_fields())
    # Convert only every other newline to CRLF -> mixed endings.
    parts = raw.split(b"\n")
    mixed = bytearray()
    for i, part in enumerate(parts[:-1]):
        mixed += part
        mixed += b"\r\n" if i % 2 == 0 else b"\n"
    mixed += parts[-1]
    r = _verify(bytes(mixed), pub)
    assert r.valid is True
    assert r.reason == "ok"


# --- Structural parse failures -----------------------------------------------


def test_duplicate_keys(key):
    priv, pub = key
    # Build a payload with two tier= lines, sign it, so we exercise the
    # duplicate-key check AFTER a valid signature.
    payload = (
        f"# jgsc-{PRODUCT} licence file\n"
        "version=1\n"
        f"product={PRODUCT}\n"
        "tier=pro\n"
        "tier=enterprise\n"
        "customer=Acme\n"
        "expires=2027-01-01\n"
    ).encode("utf-8")
    sig = _sign(priv, payload)
    raw = payload + f"signature={sig}\n".encode("utf-8")
    r = _verify(raw, pub)
    assert r.valid is False
    assert r.reason == "malformed"


def test_oversized_file(key):
    priv, pub = key
    # Size check happens first, before any parsing or signature work, so this
    # need not be validly signed. Pad past 64 KB with comment filler.
    fields = _default_fields()
    payload_head = _build_payload(fields, PRODUCT)
    filler = b"# " + b"x" * (66000) + b"\n"
    raw = filler + payload_head + b"signature=AAAA\n"
    assert len(raw) > 65536
    r = _verify(raw, pub)
    assert r.valid is False
    assert r.reason == "malformed"


def test_no_signature_line_is_malformed(key):
    priv, pub = key
    raw = _build_payload(_default_fields(), PRODUCT)  # no signature= line
    r = _verify(raw, pub)
    assert r.valid is False
    assert r.reason == "malformed"


# --- Tier canonicalization ---------------------------------------------------


@pytest.mark.parametrize("raw_tier", [" pro ", "PRO", "Pro", "  Pro  ", "\tpro\t"])
def test_tier_variants_canonicalize_to_pro(key, raw_tier):
    priv, pub = key
    raw = _mint(priv, _default_fields(tier=raw_tier))
    r = _verify(raw, pub)
    assert r.valid is True
    assert r.reason == "ok"
    assert r.tier == "pro"


@pytest.mark.parametrize("bad_tier", ["root", "", "  ", "premium", "admin"])
def test_invalid_tier(key, bad_tier):
    priv, pub = key
    raw = _mint(priv, _default_fields(tier=bad_tier))
    r = _verify(raw, pub)
    assert r.valid is False
    assert r.reason == "invalid_tier"


def test_tier_variants_enterprise_and_academic(key):
    priv, pub = key
    for tier in ("enterprise", "ACADEMIC", " Enterprise "):
        raw = _mint(priv, _default_fields(tier=tier))
        r = _verify(raw, pub)
        assert r.valid is True, tier
        assert r.tier == tier.strip().lower()


# --- Forward compatibility ---------------------------------------------------


def test_unknown_extra_field_ignored(key):
    priv, pub = key
    fields = _default_fields()
    fields["scriptkey2"] = "abc123"  # unknown field, correctly signed
    raw = _mint(priv, fields)
    r = _verify(raw, pub)
    assert r.valid is True
    assert r.reason == "ok"
    assert r.tier == "pro"


def test_value_containing_equals_and_hash(key):
    priv, pub = key
    # A value legitimately containing '=' and '#'; first-'=' split must keep it
    # whole. Use a custom field so nothing else is affected.
    fields = _default_fields()
    fields["features"] = "a=b#c,write"
    raw = _mint(priv, fields)
    r = _verify(raw, pub)
    assert r.valid is True
    assert r.reason == "ok"
    assert r.features == "a=b#c,write"


# --- expires_soon 30-day boundary --------------------------------------------


@pytest.mark.parametrize(
    "days,expected_soon",
    [(29, True), (30, True), (31, False)],
)
def test_expires_soon_boundary(key, days, expected_soon):
    priv, pub = key
    expires = (REF_DATE + timedelta(days=days)).isoformat()
    raw = _mint(priv, _default_fields(expires=expires))
    r = _verify(raw, pub)
    assert r.valid is True
    assert r.days_remaining == days
    assert r.expires_soon is expected_soon


# --- Real-mint-format fixture ------------------------------------------------


def test_real_mint_format_expired(key):
    """Mint a licence in the EXACT production byte layout (all 10 mint fields,
    including a dummy scriptkey), deliberately already expired, and verify it.

    The reason must be exactly `expired` -- proving byte-format and signature
    compatibility with the mint tool, and that scriptkey is ignored (not treated
    as an error).
    """
    priv, pub = key
    fields = {
        "version": "1",
        "product": PRODUCT,
        "tier": "pro",
        "customer": "dummy-expired-customer",
        "contact": "support@jgsystemsconsulting.com",
        "seats": "1",
        "issued": "2020-01-01",
        "expires": "2020-02-01",  # long past REF_DATE
        "features": "write,diagrams,airgap",
        "scriptkey": base64.b64encode(b"dummy-derived-script-key-32bytes").decode(),
    }
    raw = _mint(priv, fields)

    # Sanity: the minted bytes match the exact production byte layout.
    assert raw.startswith(f"# jgsc-{PRODUCT} licence file\n".encode())
    assert b"\r" not in raw  # LF-only
    assert raw.rstrip(b"\n").split(b"\n")[-1].startswith(b"signature=")

    r = _verify(raw, pub)
    assert r.valid is False
    assert r.reason == "expired"


def test_real_mint_format_valid_ignores_scriptkey(key):
    """Same production layout but unexpired -> valid; scriptkey is ignored."""
    priv, pub = key
    fields = {
        "version": "1",
        "product": PRODUCT,
        "tier": "pro",
        "customer": "dummy-customer",
        "contact": "support@jgsystemsconsulting.com",
        "seats": "1",
        "issued": "2026-01-01",
        "expires": "2027-01-01",
        "features": "write,diagrams,airgap",
        "scriptkey": base64.b64encode(b"dummy-derived-script-key-32bytes").decode(),
    }
    raw = _mint(priv, fields)
    r = _verify(raw, pub)
    assert r.valid is True
    assert r.reason == "ok"
    assert r.tier == "pro"
    assert "scriptkey" in r.fields  # parsed but not required/validated


# --- Search order / file selection (pure-function testable) ------------------


def test_directory_at_search_location_is_skipped(key, tmp_path, monkeypatch):
    """A directory named like the licence file at a higher-precedence location
    is skipped; the search continues to a real file lower down."""
    priv, pub = key

    # Higher precedence: env var points at a DIRECTORY (not a regular file).
    dir_as_licence = tmp_path / "as_dir.licence"
    dir_as_licence.mkdir()
    monkeypatch.setenv("JGS_V2_API_LICENCE_PATH", str(dir_as_licence))

    # Lower precedence: a real regular file in the home-dir location.
    home = tmp_path / "home"
    (home / ".jgs-sysmlv2-api").mkdir(parents=True)
    real_file = home / ".jgs-sysmlv2-api" / LICENCE_FILENAME
    real_file.write_bytes(_mint(priv, _default_fields()))
    monkeypatch.setattr(licence.Path, "home", staticmethod(lambda: home))

    # Also neutralize the exe-dir candidate so it can't accidentally match.
    monkeypatch.setattr(licence.sys, "argv", [str(tmp_path / "no_exe_here")])

    selected = find_licence_path()
    assert selected == real_file


def test_invalid_file_at_higher_precedence_does_not_fall_through(
    key, tmp_path, monkeypatch
):
    """An INVALID file at the highest-precedence location selects and fails --
    it does not fall through to a valid file at a lower location."""
    priv, pub = key

    # Highest precedence (env): a structurally malformed file.
    bad = tmp_path / "bad.licence"
    bad.write_bytes(b"this is not a licence at all\n")
    monkeypatch.setenv("JGS_V2_API_LICENCE_PATH", str(bad))

    # Lower precedence (home): a perfectly valid file that must NOT be reached.
    home = tmp_path / "home"
    (home / ".jgs-sysmlv2-api").mkdir(parents=True)
    good = home / ".jgs-sysmlv2-api" / LICENCE_FILENAME
    good.write_bytes(_mint(priv, _default_fields()))
    monkeypatch.setattr(licence.Path, "home", staticmethod(lambda: home))
    monkeypatch.setattr(licence.sys, "argv", [str(tmp_path / "no_exe_here")])

    r = load_licence(public_key_b64=pub, reference_date=REF_DATE)
    assert r.source == str(bad)
    assert r.valid is False
    assert r.reason == "malformed"


def test_load_licence_missing_when_no_file(tmp_path, monkeypatch):
    """No file at any search location -> reason `missing`, source None."""
    monkeypatch.delenv("JGS_V2_API_LICENCE_PATH", raising=False)
    empty_home = tmp_path / "empty_home"
    empty_home.mkdir()
    monkeypatch.setattr(licence.Path, "home", staticmethod(lambda: empty_home))
    monkeypatch.setattr(licence.sys, "argv", [str(tmp_path / "no_exe_here")])

    r = load_licence(reference_date=REF_DATE)
    assert r.valid is False
    assert r.reason == "missing"
    assert r.source is None


def test_load_licence_valid_from_env_path(key, tmp_path, monkeypatch):
    """A valid file at the env-var path is selected and verified."""
    priv, pub = key
    lic = tmp_path / "explicit.licence"
    lic.write_bytes(_mint(priv, _default_fields()))
    monkeypatch.setenv("JGS_V2_API_LICENCE_PATH", str(lic))

    r = load_licence(public_key_b64=pub, reference_date=REF_DATE)
    assert r.valid is True
    assert r.reason == "ok"
    assert r.source == str(lic)
    assert r.tier == "pro"


def test_module_imports_cleanly():
    """Smoke: the module imports and exposes the expected surface."""
    assert PRODUCT == "sysmlv2-api-pro"
    assert callable(verify_licence_bytes)
    assert callable(load_licence)
    assert callable(find_licence_path)
