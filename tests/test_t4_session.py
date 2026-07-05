# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""T4 tests — relationship staging, caller-minted ids, batch atomicity."""
import copy

import pytest

from jgs_sysmlv2_api_mcp.session import Session, StagingError


def _payload_of(session, eid):
    return next(o["payload"] for o in session.staged_ops() if o["id"] == eid)


def test_create_relationship_sets_source_target_and_mapped_ends():
    s = Session(project="p")
    rid = s.create_relationship(type="Subclassification", source="car", target="vehicle")
    p = _payload_of(s, rid)
    assert p["@type"] == "Subclassification"
    assert p["source"] == [{"@id": "car"}]                  # D4: explicit arrays
    assert p["target"] == [{"@id": "vehicle"}]
    assert p["subclassifier"] == {"@id": "car"}             # D10: concrete ends
    assert p["superclassifier"] == {"@id": "vehicle"}


def test_create_relationship_dependency_uses_array_ends():
    s = Session(project="p")
    rid = s.create_relationship(type="Dependency", source="a", target="b")
    p = _payload_of(s, rid)
    assert p["client"] == [{"@id": "a"}]                    # D10: array ends (GT 21)
    assert p["supplier"] == [{"@id": "b"}]


def test_create_relationship_unknown_type_gets_properties_passthrough():
    s = Session(project="p")
    rid = s.create_relationship(type="Allocation", source="a", target="b",
                                properties={"declaredName": "alloc1"})
    p = _payload_of(s, rid)
    assert p["source"] == [{"@id": "a"}] and p["target"] == [{"@id": "b"}]
    assert p["declaredName"] == "alloc1"
    assert "client" not in p                                # no invented ends


def test_create_relationship_with_owner_synthesizes_membership():
    s = Session(project="p")
    rid = s.create_relationship(type="Specialization", source="a", target="b",
                                owner="pkg")
    ops = s.staged_ops()
    assert len(ops) == 2
    membership = ops[1]["payload"]
    assert membership["@type"] == "OwningMembership"
    assert membership["owningRelatedElement"] == {"@id": "pkg"}
    assert membership["ownedMemberElement"] == {"@id": rid}


def test_create_element_accepts_caller_minted_id():
    s = Session(project="p")
    eid = s.create_element(type="Package", name="Pkg", owner="root",
                           element_id="11111111-1111-1111-1111-111111111111")
    assert eid == "11111111-1111-1111-1111-111111111111"    # D12 cross-ref hook
    assert _payload_of(s, eid)["@id"] == eid


def test_stage_batch_cross_references_and_returns_ids():
    s = Session(project="p")
    pkg = "22222222-2222-2222-2222-222222222222"
    staged = s.stage_batch([
        {"op": "create", "type": "Package", "name": "Pkg", "owner": "root",
         "element_id": pkg},
        {"op": "create", "type": "PartDefinition", "name": "Car", "owner": pkg},
    ])
    assert staged[0] == pkg
    # each create stages element + membership -> 4 ops total
    assert len(s.staged_ops()) == 4
    car_membership = s.staged_ops()[3]["payload"]
    assert car_membership["owningRelatedElement"] == {"@id": pkg}   # in-batch ref


def test_stage_batch_rolls_back_wholesale_on_failure():
    s = Session(project="p")
    s.create_element(type="Package", name="Existing", owner="root")
    before = s.staged_ops()
    with pytest.raises(StagingError, match="unknown batch op"):
        s.stage_batch([
            {"op": "create", "type": "PartDefinition", "name": "X", "owner": "root"},
            {"op": "explode", "element_id": "whatever"},
        ])
    assert s.staged_ops() == before                          # D12: all-or-nothing


def test_stage_batch_modify_and_delete_ops():
    s = Session(project="p")
    staged = s.stage_batch([
        {"op": "modify", "element_id": "real1", "changes": {"declaredName": "renamed"}},
        {"op": "delete", "element_id": "real2"},
    ])
    assert staged == ["real1", "real2"]
    kinds = [(o["op"], o["id"]) for o in s.staged_ops()]
    assert ("modify", "real1") in kinds and ("delete", "real2") in kinds


def test_stage_batch_rollback_reverts_in_place_mutation_of_preexisting_op():
    # regression guard for the shallow-snapshot bug class: stage_batch's
    # snapshot must be a genuine deep copy of payload dicts, not just a
    # fresh outer list sharing the same payload dict references. Proof:
    # 1) pre-stage a create for `eid`, 2) run a batch whose first op is a
    # modify targeting `eid` (hits modify_element's create-merge path,
    # `o["payload"].update(changes)`, which mutates that staged op's
    # payload dict IN PLACE), 3) the batch's second op fails, forcing
    # rollback. A shallow `list(self._ops)` snapshot would restore the
    # ops list but the mutated payload dict would still be shared/mutated
    # — the assertion below would then fail.
    s = Session(project="p")
    eid = s.create_element(type="Package", name="Original", owner="root")
    original_payload = copy.deepcopy(_payload_of(s, eid))
    with pytest.raises(StagingError, match="unknown batch op"):
        s.stage_batch([
            {"op": "modify", "element_id": eid, "changes": {"declaredName": "mutated"}},
            {"op": "explode", "element_id": "whatever"},
        ])
    assert _payload_of(s, eid) == original_payload            # D12: mutation reverted, not just op list


def test_stage_batch_with_preexisting_delete_in_buffer_does_not_crash():
    # regression: a real-element delete stages payload=None; the snapshot
    # must not call dict(None) on it when a LATER batch runs
    s = Session(project="p")
    s.delete_element("real3")
    staged = s.stage_batch([
        {"op": "create", "type": "PartDefinition", "name": "Y", "owner": "root"},
    ])
    assert len(staged) == 1
