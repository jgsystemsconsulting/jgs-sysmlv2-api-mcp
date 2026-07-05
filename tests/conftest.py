# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""Shared test fixtures for licence minting.

Provides a reusable Ed25519 test keypair and a `mint_licence` factory that
produces licence file bytes in the EXACT production byte layout
(``cameo-sysmlv2-mcp/licensing/sign_licence.py``: LF-only, ``# jgsc-<product>
licence file`` header, ``key=value`` lines in field order, ``signature=`` last).

These mirror the private minting helpers in ``test_licence.py`` so the
integration tests in ``test_licence_gate.py`` can build valid/invalid licence
FILES without duplicating the byte-format logic. No real production key is used
anywhere; every fixture is minted with a locally generated test key and verified
against that same key via the pubkey seam.
"""
from __future__ import annotations

import base64
from datetime import date

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from jgs_sysmlv2_api_mcp.licence import PRODUCT

# Field ordering the real mint tool (sign_licence.py REQUIRED_FIELDS) uses.
# The verifier is order-independent, but mirroring it proves byte-format
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

#: Fixed reference date -> clock-independent tests.
REF_DATE = date(2026, 7, 4)


def _make_key() -> tuple[Ed25519PrivateKey, str]:
    """Return (private_key, public_key_b64) for a fresh test keypair."""
    priv = Ed25519PrivateKey.generate()
    raw_pub = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return priv, base64.b64encode(raw_pub).decode("ascii")


def _build_payload(fields: dict, product: str) -> bytes:
    """Header + ordered ``key=value`` lines (mirrors sign_licence build_payload)."""
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


def default_fields(**overrides) -> dict:
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
def test_key():
    """A fresh Ed25519 test keypair as (private_key, public_key_b64)."""
    return _make_key()


@pytest.fixture()
def mint_licence(test_key):
    """Factory: mint signed licence bytes for the shared test keypair.

    Usage::

        raw = mint_licence()                       # valid PRO, unexpired
        raw = mint_licence(tier="free")            # explicit FREE
        raw = mint_licence(expires="2020-01-01")   # expired

    Returns the licence file bytes. The matching public key (base64) is the
    second element of the ``test_key`` fixture.
    """
    priv, _pub = test_key

    def _factory(**field_overrides) -> bytes:
        return _mint(priv, default_fields(**field_overrides))

    return _factory
