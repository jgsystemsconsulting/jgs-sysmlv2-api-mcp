# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""Task 9 — commit body builder (spec §4 commit flow).

SPIKE CORRECTION applied: the pilot's POST body is a CommitRequest, NOT a
Commit — it has NO top-level @id (the server assigns the commit id; see
SPIKE RESULT + ground truth #1 in tests/test_spike_write_roundtrip.py).
build_commit_body therefore returns JUST the body dict, never a
(commit_id, body) tuple and never a client-minted @id.
"""
from jgs_sysmlv2_api_mcp.tools.commit_tools import build_commit_body


def test_build_commit_body_returns_bare_body_with_no_top_level_id():
    ops = [
        {"op": "create", "id": "a", "payload": {"@id": "a", "@type": "PartDefinition"}},
        {"op": "delete", "id": "b", "payload": None, "identity": {"@id": "b"}},
    ]
    body = build_commit_body(ops, previous_commit="head1")
    assert isinstance(body, dict)
    assert "@id" not in body                      # server assigns the commit id
    assert body["@type"] == "Commit"
    assert body["previousCommit"] == {"@id": "head1"}
    assert len(body["change"]) == 2


def test_create_op_shapes_datachange_payload_and_identity():
    ops = [{"op": "create", "id": "a", "payload": {"@id": "a", "@type": "PartDefinition"}}]
    body = build_commit_body(ops, previous_commit="head1")
    change0 = body["change"][0]
    assert change0["@type"] == "DataVersion"
    assert change0["payload"]["@id"] == "a"
    assert change0["identity"]["@id"] == "a"
    assert change0["identity"]["@type"] == "DataIdentity"


def test_delete_op_has_null_payload():
    ops = [{"op": "delete", "id": "b", "payload": None, "identity": {"@id": "b"}}]
    body = build_commit_body(ops, previous_commit="head1")
    change0 = body["change"][0]
    assert change0["payload"] is None
    assert change0["identity"]["@id"] == "b"


def test_no_previous_commit_omits_previous_commit_key():
    ops = [{"op": "create", "id": "new1", "payload": {"@id": "new1", "@type": "PartDefinition"}}]
    body = build_commit_body(ops, previous_commit=None)
    assert "previousCommit" not in body


def test_modify_op_threads_prior_version_into_identity():
    # real-element modify must version against its prior DataVersion (M1/spec §4)
    ops = [{"op": "modify", "id": "real1",
            "payload": {"@id": "real1", "declaredName": "X"},
            "identity": {"@id": "real1"}, "prior_version": "ver-7"}]
    body = build_commit_body(ops, previous_commit="head1")
    ident = body["change"][0]["identity"]
    assert ident["@id"] == "real1"
    assert ident["identity"] == {"@id": "ver-7"}   # prior version linked


def test_create_op_has_no_prior_version_link():
    # a fresh create has no prior_version -> identity carries only @id (+ @type)
    ops = [{"op": "create", "id": "new1", "payload": {"@id": "new1", "@type": "PartDefinition"}}]
    body = build_commit_body(ops, previous_commit=None)
    ident = body["change"][0]["identity"]
    assert ident["@id"] == "new1"
    assert "identity" not in ident   # no prior link


def test_delete_op_with_prior_version_threads_identity_too():
    # deleting a real element also versions against its prior DataVersion
    ops = [{"op": "delete", "id": "real2", "payload": None,
            "identity": {"@id": "real2"}, "prior_version": "ver-3"}]
    body = build_commit_body(ops, previous_commit="head1")
    change0 = body["change"][0]
    assert change0["payload"] is None
    assert change0["identity"]["identity"] == {"@id": "ver-3"}


def test_build_commit_body_preserves_op_order():
    ops = [
        {"op": "create", "id": "a", "payload": {"@id": "a", "@type": "PartDefinition"}},
        {"op": "create", "id": "b", "payload": {"@id": "b", "@type": "PartDefinition"}},
        {"op": "delete", "id": "c", "payload": None, "identity": {"@id": "c"}},
    ]
    body = build_commit_body(ops, previous_commit="head1")
    assert [c["identity"]["@id"] for c in body["change"]] == ["a", "b", "c"]
