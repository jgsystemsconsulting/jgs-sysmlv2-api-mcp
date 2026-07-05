# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""T2 tests — session branch retargeting (D6/D8)."""
import pytest

from jgs_sysmlv2_api_mcp.session import Session, StagingError


def test_branch_defaults_to_none_and_init_kwarg_sets_it():
    assert Session(project="p").branch is None
    assert Session(project="p", branch="b1").branch == "b1"


def test_set_branch_with_empty_buffer_retargets_and_kills_token():
    s = Session(project="p")
    s.create_element(type="PartDefinition", name="X", owner="root")
    s.discard()                                  # buffer empty again
    s.review_changes()                           # issue a token (empty buffer is fine)
    s.set_branch("b2")
    assert s.branch == "b2"
    from jgs_sysmlv2_api_mcp.session import TokenError
    with pytest.raises(TokenError):
        s.verify_and_consume("anything")         # old token gone


def test_set_branch_refuses_with_staged_work():
    s = Session(project="p", branch="b1")
    s.create_element(type="PartDefinition", name="X", owner="root")
    with pytest.raises(StagingError, match="commit or discard"):
        s.set_branch("b2")
    assert s.branch == "b1"                      # unchanged
    assert len(s.staged_ops()) == 2              # buffer preserved
