# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
import hashlib
import json
import uuid


def new_uuid() -> str:
    return str(uuid.uuid4())


def _referenced_ids(ops: list[dict]) -> set[str]:
    refs: set[str] = set()
    for op in ops:
        refs.update(op.get("refs", []))
    return refs


def fingerprint(ops: list[dict], prior_versions: dict[str, str]) -> str:
    """Hash the ordered op-list + ONLY the prior-versions of referenced real elements.
    Unrelated head movement (prior-version of an unreferenced element) does not change it."""
    referenced = _referenced_ids(ops)
    scoped_prior = {k: v for k, v in prior_versions.items() if k in referenced}
    material = json.dumps(
        {"ops": ops, "prior": dict(sorted(scoped_prior.items()))},
        sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(material.encode()).hexdigest()
