# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
import pytest

from jgs_sysmlv2_api_mcp.session import Session, StagingError


class FakeResolver:
    """Resolves a real UUID to its (project, prior_version) and its owned children."""
    def __init__(self, mapping, children=None):
        self.mapping = mapping
        self._children = children or {}          # uuid -> [child_uuid, ...]
    def resolve(self, uuid): return self.mapping.get(uuid)   # -> {"project":..., "version":...} or None
    def owned_children(self, uuid): return self._children.get(uuid, [])


def test_cross_project_owner_rejected():
    s = Session(project="p", buffer_cap=100,
                resolver=FakeResolver({"foreign": {"project": "OTHER", "version": "v1"}}))
    with pytest.raises(StagingError, match="cross-project"):
        s.create_element(type="PartDefinition", name="A", owner="foreign")


def test_delete_element_with_children_errors():   # SC6: bounded delete, no cascade
    s = Session(project="p", buffer_cap=100,
                resolver=FakeResolver({"parent": {"project": "p", "version": "v1"}},
                                      children={"parent": ["kid1", "kid2"]}))
    with pytest.raises(StagingError, match="owns 2 child"):
        s.delete_element("parent")
    assert s.staged_ops() == []   # nothing staged on rejection


def test_sc3a_client_prevalidation_blocks_before_commit():
    # SC3a: a known-bad input is rejected at STAGE time, so nothing is ever
    # staged and no commit can be sent (the commit-never-leaves-the-client path,
    # distinct from SC3b server atomicity).
    s = Session(project="p", buffer_cap=100,
                resolver=FakeResolver({"foreign": {"project": "OTHER", "version": "v1"}}))
    with pytest.raises(StagingError):
        s.create_element(type="PartDefinition", name="A", owner="foreign")
    assert s.staged_ops() == []   # buffer empty -> build_commit_body would be a no-op


def test_modify_real_element_stages_changed_with_prior():
    s = Session(project="p", buffer_cap=100,
                resolver=FakeResolver({"real1": {"project": "p", "version": "v1"}}))
    s.modify_element("real1", {"declaredName": "Renamed"})
    op = s.staged_ops()[0]
    assert op["op"] == "modify" and op["id"] == "real1"
    assert "real1" in op["refs"]


def test_modify_then_delete_real_collapses_to_delete():
    s = Session(project="p", buffer_cap=100,
                resolver=FakeResolver({"real1": {"project": "p", "version": "v1"}}))
    s.modify_element("real1", {"declaredName": "X"})
    s.delete_element("real1")
    ops = [o for o in s.staged_ops() if o["id"] == "real1"]
    assert len(ops) == 1 and ops[0]["op"] == "delete"
