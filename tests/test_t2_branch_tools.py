# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""T2 tests — client-side squash-merge machinery (pilot has no native merge)."""
from unittest.mock import MagicMock

from jgs_sysmlv2_api_mcp.tools.branch_tools import (
    delete_branch_verified,
    find_divergence,
    squash_merge,
)

#  c1 -- c2 -- c3          (main)
#          \-- b1 -- b2    (work)
COMMITS = [
    {"@id": "c1", "previousCommit": None},
    {"@id": "c2", "previousCommit": {"@id": "c1"}},
    {"@id": "c3", "previousCommit": {"@id": "c2"}},
    {"@id": "b1", "previousCommit": {"@id": "c2"}},
    {"@id": "b2", "previousCommit": {"@id": "b1"}},
]


def test_find_divergence_forked_lineages():
    assert find_divergence(COMMITS, "b2", "c3") == "c2"


def test_find_divergence_fast_forward_and_disjoint():
    assert find_divergence(COMMITS, "b2", "c2") == "c2"      # target is ancestor
    disjoint = [{"@id": "x1", "previousCommit": None},
                {"@id": "y1", "previousCommit": None}]
    assert find_divergence(disjoint, "x1", "y1") is None


def _merge_api(elements_by_commit, branches, commits=COMMITS):
    api = MagicMock()
    api.get_branch.side_effect = lambda bid: branches[bid]
    api.get_commits.return_value = commits
    api.get_elements.side_effect = lambda cid: list(elements_by_commit[cid].values())
    api.get_element.side_effect = lambda cid, eid: elements_by_commit[cid][eid]
    api.post_commit.return_value = {"@id": "merged1"}
    return api


BRANCHES = {"work": {"@id": "work", "head": {"@id": "b2"}},
            "main": {"@id": "main", "head": {"@id": "c3"}}}


def test_squash_merge_conflict_when_both_sides_touch_same_element():
    els = {
        "c2": {"E": {"@id": "E", "declaredName": "E0"}},
        "c3": {"E": {"@id": "E", "declaredName": "E-main"}},   # main changed E
        "b2": {"E": {"@id": "E", "declaredName": "E-work"}},   # work changed E too
    }
    api = _merge_api(els, BRANCHES)
    got = squash_merge(api, "work", "main")
    assert got == {"outcome": "conflict", "elements": ["E"]}
    api.post_commit.assert_not_called()                        # D7: merges nothing


def test_squash_merge_replays_net_change_onto_target():
    els = {
        "c2": {"E": {"@id": "E", "declaredName": "E0"}},
        "c3": {"E": {"@id": "E", "declaredName": "E0"},        # main: unrelated new G
               "G": {"@id": "G", "declaredName": "G"}},
        "b2": {"F": {"@id": "F", "declaredName": "F"}},        # work: +F, -E
    }
    api = _merge_api(els, BRANCHES)
    got = squash_merge(api, "work", "main", description="merge work")
    assert got["outcome"] == "merged" and got["commit_id"] == "merged1"
    assert got["created"] == ["F"] and got["deleted"] == ["E"]
    body = api.post_commit.call_args[0][0]
    assert api.post_commit.call_args[1]["branch_id"] == "main"
    assert body["previousCommit"] == {"@id": "c3"}
    assert body["description"] == "merge work"
    payloads = {c["identity"]["@id"]: c["payload"] for c in body["change"]}
    assert payloads["F"]["declaredName"] == "F"                # verbatim replay (GT 15)
    assert payloads["E"] is None                               # prior-less delete (GT 13)


def test_squash_merge_nothing_to_merge_when_source_at_divergence():
    branches = {"work": {"@id": "work", "head": {"@id": "c2"}},
                "main": {"@id": "main", "head": {"@id": "c3"}}}
    api = _merge_api({"c2": {}, "c3": {}}, branches)
    assert squash_merge(api, "work", "main") == {"outcome": "nothing-to-merge"}


def test_delete_branch_verified_refuses_default_and_verifies_list():
    api = MagicMock()
    api.get_project.return_value = {"defaultBranch": {"@id": "main"}}
    got = delete_branch_verified(api, "main")
    assert got["deleted"] is False and "default" in got["reason"]
    api.delete_branch.assert_not_called()
    # non-default: DELETE fired, outcome read from the follow-up list (GT 11)
    api.get_branches.return_value = [{"@id": "main"}]
    got = delete_branch_verified(api, "work")
    api.delete_branch.assert_called_once_with("work")
    assert got == {"deleted": True}
