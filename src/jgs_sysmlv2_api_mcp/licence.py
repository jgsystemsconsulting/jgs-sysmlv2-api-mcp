# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""Offline Ed25519 licence verification for sysmlv2-api-pro.

Pure-Python port of the Java ``LicenceVerifier`` semantics (see the licensing
design spec, section 2). Verifies a signed LF-only properties-file licence,
returning a structured :class:`LicenceResult`. No telemetry, no phone-home,
fully offline. Enforcement is deterrence, not DRM.

The verify function takes the Ed25519 public key as a parameter defaulting to
the embedded module constant :data:`EMBEDDED_PUBLIC_KEY_B64`; that seam exists
so unit tests can pass a test keypair's public key. The compiled binary never
overrides it.
"""
from __future__ import annotations

import base64
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

log = logging.getLogger(__name__)

# --- Constants ---------------------------------------------------------------

#: Product slug this verifier accepts (spec section 1).
PRODUCT = "sysmlv2-api-pro"

#: Supported licence format version. Field values are always strings, so the
#: comparison target is the string ``"1"``.
VERSION = "1"

#: Filename the search order looks for under the exe dir and the home dir.
LICENCE_FILENAME = "jgsc-sysmlv2-api-pro.licence"

#: Environment variable holding an explicit licence path (highest precedence).
LICENCE_PATH_ENV = "JGS_V2_API_LICENCE_PATH"

#: Maximum licence file size (64 KB). Larger files are rejected before parsing.
MAX_FILE_BYTES = 65536

#: Maximum length of any single field value (4 KB).
MAX_VALUE_BYTES = 4096

#: Canonical tier vocabulary (spec section 1). ``tier`` is compared after
#: ``.strip().lower()`` and the canonical form is what the result reports.
VALID_TIERS = frozenset({"free", "pro", "enterprise", "academic"})

#: Required fields that must be present in a well-formed licence payload.
REQUIRED_FIELDS = ("product", "version", "expires", "tier")

#: Days-before-expiry window (inclusive) that flips ``expires_soon`` to True.
EXPIRES_SOON_DAYS = 30

#: Regex a licence key must match. A key-shaped line that fails this is treated
#: as a structurally corrupt (hand-edited) file -> ``malformed``.
_KEY_RE = re.compile(r"^[a-z0-9_]+$")

#: Embedded Ed25519 public key (base64, 32 raw bytes).
#:
#: Real production key for the sysmlv2-api-pro product, minted by the vendor
#: toolchain (cameo-sysmlv2-mcp/licensing/keys/jgs-sysmlv2-api.pub). The
#: matching private key never leaves the vendor machine.
EMBEDDED_PUBLIC_KEY_B64 = "uQ4jU6C74jmXfBDyElofEH1VWkR+hdglWiQFnPtnyBY="

# The exact set of failure reason codes exposed to callers / MCP clients
# (spec section 2). Exactly eight, no more.
REASON_MISSING = "missing"
REASON_UNREADABLE = "unreadable"
REASON_MALFORMED = "malformed"
REASON_BAD_SIGNATURE = "bad_signature"
REASON_UNSUPPORTED_VERSION = "unsupported_version"
REASON_WRONG_PRODUCT = "wrong_product"
REASON_INVALID_TIER = "invalid_tier"
REASON_EXPIRED = "expired"


class _LicenceError(Exception):
    """Internal control-flow signal carrying a failure reason code."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class LicenceResult:
    """Structured outcome of verifying a licence.

    ``reason`` is ``"ok"`` when ``valid`` is True, otherwise one of the eight
    failure reason codes. ``tier`` is the canonicalized (stripped + lowercased)
    tier, never the raw field string.
    """

    valid: bool
    reason: str = "ok"
    tier: str | None = None
    customer: str | None = None
    expires: str | None = None
    days_remaining: int | None = None
    expires_soon: bool = False
    seats: str | None = None
    features: str | None = None
    source: str | None = None
    fields: dict[str, str] = field(default_factory=dict)


# --- Public key handling -----------------------------------------------------


def _load_public_key(pub_b64: str) -> Ed25519PublicKey:
    """Decode a base64 raw-32-byte Ed25519 public key."""
    raw = base64.b64decode(pub_b64)
    return Ed25519PublicKey.from_public_bytes(raw)


# --- Field parsing -----------------------------------------------------------


def _parse_fields(payload: str) -> dict[str, str]:
    """Parse ``key=value`` fields from the signed payload.

    Comment lines (starting with ``#``) and blank lines are skipped. Each other
    line is split on the FIRST ``=`` only (values may contain ``=`` and ``#``).
    Keys must match ``[a-z0-9_]+``; values are capped at 4 KB; duplicate keys
    are rejected. Any structural violation raises ``_LicenceError(malformed)``.
    """
    fields: dict[str, str] = {}
    for line in payload.split("\n"):
        if line == "" or line.startswith("#"):
            continue
        if "=" not in line:
            # A non-comment, non-blank line with no '=' is a corrupt/hand-edited
            # structure.
            raise _LicenceError(REASON_MALFORMED, f"line without '=': {line!r}")
        key, value = line.split("=", 1)
        if not _KEY_RE.match(key):
            raise _LicenceError(REASON_MALFORMED, f"invalid key: {key!r}")
        if len(value.encode("utf-8")) > MAX_VALUE_BYTES:
            raise _LicenceError(REASON_MALFORMED, f"value too large for key {key!r}")
        if key in fields:
            raise _LicenceError(REASON_MALFORMED, f"duplicate key: {key!r}")
        fields[key] = value
    return fields


# --- Core verification -------------------------------------------------------


def verify_licence_bytes(
    raw: bytes,
    *,
    public_key_b64: str = EMBEDDED_PUBLIC_KEY_B64,
    reference_date: date | None = None,
    source: str | None = None,
) -> LicenceResult:
    """Verify raw licence bytes and return a :class:`LicenceResult`.

    Args:
        raw: The exact bytes of the licence file.
        public_key_b64: Ed25519 public key (base64, raw 32 bytes). Defaults to
            the embedded constant; the unit-test seam passes a test key here.
        reference_date: Date to evaluate expiry against (default: UTC today).
            Injectable so expiry tests are clock-independent.
        source: Absolute path of the selected file, echoed into the result.
    """
    if reference_date is None:
        reference_date = datetime.now(timezone.utc).date()

    try:
        fields = _verify_and_parse(raw, public_key_b64, reference_date)
    except _LicenceError as exc:
        if exc.detail:
            log.warning("licence rejected (%s): %s", exc.reason, exc.detail)
        else:
            log.warning("licence rejected (%s)", exc.reason)
        return LicenceResult(valid=False, reason=exc.reason, source=source)

    tier = fields["tier"].strip().lower()
    expires_str = fields["expires"]
    exp_date = date.fromisoformat(expires_str)  # already validated in _verify_and_parse
    days_remaining = (exp_date - reference_date).days
    expires_soon = 0 <= days_remaining <= EXPIRES_SOON_DAYS

    return LicenceResult(
        valid=True,
        reason="ok",
        tier=tier,
        customer=fields.get("customer"),
        expires=expires_str,
        days_remaining=days_remaining,
        expires_soon=expires_soon,
        seats=fields.get("seats"),
        features=fields.get("features"),
        source=source,
        fields=fields,
    )


def _verify_and_parse(
    raw: bytes, public_key_b64: str, reference_date: date
) -> dict[str, str]:
    """Run the ordered verification steps; raise ``_LicenceError`` on failure.

    Returns the parsed field dict on success.
    """
    # Step 1: size cap BEFORE any parsing.
    if len(raw) > MAX_FILE_BYTES:
        raise _LicenceError(REASON_MALFORMED, f"file too large: {len(raw)} bytes")

    # Decode + normalize CRLF -> LF (mixed line endings normalize identically).
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _LicenceError(REASON_MALFORMED, f"not valid UTF-8: {exc}") from exc
    content = content.replace("\r\n", "\n").replace("\r", "\n")

    # Step 3: split payload at "signature=".
    marker = "signature="
    idx = content.find(marker)
    if idx == -1:
        raise _LicenceError(REASON_MALFORMED, "no signature= line")
    payload = content[:idx]

    # Extract the signature line's value (up to end-of-line), base64-decode it.
    sig_line = content[idx + len(marker):].split("\n", 1)[0]
    try:
        signature = base64.b64decode(sig_line, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise _LicenceError(REASON_MALFORMED, f"signature not base64: {exc}") from exc

    # Step 4: Ed25519 verify payload bytes against the public key.
    try:
        public_key = _load_public_key(public_key_b64)
    except (ValueError, base64.binascii.Error) as exc:
        # A malformed public key is a configuration error, not a licence fault;
        # surface it loudly rather than silently mapping to a licence reason.
        raise ValueError(f"invalid embedded/parameter public key: {exc}") from exc
    try:
        public_key.verify(signature, payload.encode("utf-8"))
    except InvalidSignature as exc:
        raise _LicenceError(REASON_BAD_SIGNATURE, "signature check failed") from exc

    # Step 5: parse fields from the (signed) payload.
    fields = _parse_fields(payload)

    # Step 6: required fields present.
    missing = [k for k in REQUIRED_FIELDS if k not in fields]
    if missing:
        raise _LicenceError(REASON_MISSING, f"missing required fields: {missing}")

    # Step 7: version.
    if fields["version"] != VERSION:
        raise _LicenceError(
            REASON_UNSUPPORTED_VERSION, f"version={fields['version']!r}"
        )

    # Step 8: product.
    if fields["product"] != PRODUCT:
        raise _LicenceError(REASON_WRONG_PRODUCT, f"product={fields['product']!r}")

    # Step 9: tier (canonicalized).
    tier = fields["tier"].strip().lower()
    if tier not in VALID_TIERS:
        raise _LicenceError(REASON_INVALID_TIER, f"tier={fields['tier']!r}")

    # Step 10: expiry. An invalid ISO date is structural -> malformed; a valid
    # date in the past is -> expired. Valid ON the expiry date, invalid the day
    # after (expires >= reference_date is valid).
    try:
        exp_date = date.fromisoformat(fields["expires"])
    except ValueError as exc:
        raise _LicenceError(
            REASON_MALFORMED, f"invalid expires date: {fields['expires']!r}"
        ) from exc
    if exp_date < reference_date:
        raise _LicenceError(REASON_EXPIRED, f"expired on {fields['expires']}")

    return fields


# --- Licence search order ----------------------------------------------------


def _candidate_paths() -> list[Path]:
    """Return the ordered list of candidate licence paths (spec section 2).

    1. ``JGS_V2_API_LICENCE_PATH`` env var (explicit path).
    2. The deployed executable's directory. Resolved via ``sys.argv[0]``,
       explicitly NOT ``sys.executable``: in Nuitka onefile mode
       ``sys.executable`` points into the temp unpack dir, which makes this path
       dead. ``sys.argv[0]`` is the path the launcher was invoked as.
    3. ``~/.jgs-sysmlv2-api/jgsc-sysmlv2-api-pro.licence``.
    """
    candidates: list[Path] = []

    env_path = os.environ.get(LICENCE_PATH_ENV)
    if env_path:
        candidates.append(Path(env_path))

    try:
        exe_dir = Path(sys.argv[0]).resolve().parent
        candidates.append(exe_dir / LICENCE_FILENAME)
    except (OSError, ValueError):
        # sys.argv[0] may be empty or unresolvable in some embeddings; skip.
        pass

    candidates.append(Path.home() / ".jgs-sysmlv2-api" / LICENCE_FILENAME)
    return candidates


def find_licence_path() -> Path | None:
    """Return the first EXISTING regular file among the search candidates.

    A directory or other non-regular-file at a search location is skipped and
    the search continues to the next candidate. Returns None if no candidate is
    an existing regular file.
    """
    for path in _candidate_paths():
        try:
            if path.is_file():  # follows symlinks; False for dirs / missing
                return path
        except OSError:
            # e.g. permission error stat-ing the path -- treat as absent, keep
            # searching. (Read-time permission errors are handled in load_licence.)
            continue
    return None


def load_licence(
    *,
    public_key_b64: str = EMBEDDED_PUBLIC_KEY_B64,
    reference_date: date | None = None,
) -> LicenceResult:
    """Locate, read and verify the licence; the server calls this once at start.

    Returns a full :class:`LicenceResult`. When no file is found at any search
    location the result is ``missing`` with ``source=None``. When a file is
    found but cannot be read (permissions / locked) the result is ``unreadable``.
    An invalid file at a higher-precedence location does NOT fall through -- it
    is selected, fails verification, and its reason is returned.
    """
    path = find_licence_path()
    if path is None:
        log.warning("no licence file found (%s)", REASON_MISSING)
        return LicenceResult(valid=False, reason=REASON_MISSING, source=None)

    source = str(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        log.warning("licence unreadable (%s): %s", REASON_UNREADABLE, exc)
        return LicenceResult(valid=False, reason=REASON_UNREADABLE, source=source)

    return verify_licence_bytes(
        raw,
        public_key_b64=public_key_b64,
        reference_date=reference_date,
        source=source,
    )
