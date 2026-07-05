# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
import pytest

from jgs_sysmlv2_api_mcp.session import Session, StagingError


def test_create_stages_element_plus_membership():
    s = Session(project="p", buffer_cap=100)
    eid = s.create_element(type="PartDefinition", name="Vehicle", owner="root-uuid")
    ops = s.staged_ops()
    kinds = [(o["op"], o["payload"]["@type"]) for o in ops]
    assert ("create", "PartDefinition") in kinds
    assert ("create", "OwningMembership") in kinds   # synthesized
    assert eid  # returns the element uuid


def test_create_then_delete_same_id_drops_out():
    s = Session(project="p", buffer_cap=100)
    eid = s.create_element(type="PartDefinition", name="X", owner="root")
    s.delete_element(eid)
    assert s.staged_ops() == []   # element + its membership both gone


def test_buffer_cap_rejects_and_preserves():
    # cap=2: first create stages exactly 2 ops (element + membership) and fits;
    # the second create would need 2 more (total 4 > 2) and must be rejected.
    s = Session(project="p", buffer_cap=2)
    s.create_element(type="PartDefinition", name="A", owner="root")
    before = list(s.staged_ops())
    assert len(before) == 2
    with pytest.raises(StagingError, match="buffer full"):
        s.create_element(type="PartDefinition", name="B", owner="root")
    assert s.staged_ops() == before   # nothing dropped
