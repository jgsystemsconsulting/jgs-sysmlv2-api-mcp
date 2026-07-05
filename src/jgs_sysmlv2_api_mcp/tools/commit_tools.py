# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""Commit body builder (spec §4 commit flow).

SPIKE CORRECTION (SPIKE RESULT, ground truth #1 — see
tests/test_spike_write_roundtrip.py): the pilot's POST body is a
CommitRequest, NOT a Commit. It has NO top-level @id — the SERVER assigns the
commit id in its response. build_commit_body therefore returns JUST the body
dict (never a (commit_id, body) tuple, never a client-minted @id).

Real-element ops (modify/delete) carry the element's prior_version so the API
versions the DataVersion against the existing element instead of treating it
as a fresh create. A DataVersion whose identity has NO prior version is a
create; one WITH a prior version links to it via identity.identity
(spec §4 real-element writes).
"""


def build_commit_body(ops: list[dict], previous_commit: str | None) -> dict:
    """Build a CommitRequest body (no top-level @id — server assigns the
    commit id) from a list of staged ops. Each op is a dict with at least
    `op` ("create" | "modify" | "delete"), `id`, and `payload`
    (None for delete). Real-element modify/delete ops additionally carry
    `prior_version`, which is threaded into `identity.identity` so the API
    versions against the element's prior DataVersion rather than a create.
    """
    change = []
    for o in ops:
        identity = {"@id": o["id"], "@type": "DataIdentity"}
        prior = o.get("prior_version")
        if prior:
            identity["identity"] = {"@id": prior}   # link to the prior DataVersion
        change.append({
            "@type": "DataVersion",
            "payload": o["payload"],   # None for delete; op payload otherwise
            "identity": identity,
        })

    body = {"@type": "Commit", "change": change}
    if previous_commit:
        body["previousCommit"] = {"@id": previous_commit}
    return body
