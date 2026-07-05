# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
from jgs_sysmlv2_api_mcp.ids import new_uuid, fingerprint


def test_new_uuid_is_unique():
    assert new_uuid() != new_uuid()


def test_fingerprint_stable_for_same_ops():
    ops = [{"op": "create", "id": "a", "type": "PartDefinition"}]
    prior = {"real1": "ver1"}
    assert fingerprint(ops, prior) == fingerprint(ops, prior)


def test_fingerprint_changes_when_ops_change():
    prior = {}
    f1 = fingerprint([{"op": "create", "id": "a"}], prior)
    f2 = fingerprint([{"op": "create", "id": "a"}, {"op": "create", "id": "b"}], prior)
    assert f1 != f2


def test_fingerprint_ignores_unrelated_prior_versions():
    # per-referenced-element scoping: prior-version of an element NOT referenced must not matter.
    ops = [{"op": "modify", "id": "a", "refs": ["a"]}]
    assert fingerprint(ops, {"a": "v1"}) != fingerprint(ops, {"a": "v2"})   # referenced -> matters
    assert fingerprint(ops, {"a": "v1", "z": "v1"}) == fingerprint(ops, {"a": "v1", "z": "v9"})  # z unreferenced
