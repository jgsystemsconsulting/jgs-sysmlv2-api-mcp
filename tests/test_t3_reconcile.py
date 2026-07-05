# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""T3 regression — reconcile() must key on the session BRANCH's head.

The T2-documented defect: reconcile()'s project-wide commit walk treats a
pre-existing SIBLING commit on another branch (same parent as our branch
head — ordinary after create_branch, no concurrency needed) as proof the
ambiguous write landed. With resolve_head provided, the verdict comes from
the authoritative branch head instead."""
from unittest.mock import MagicMock

from jgs_sysmlv2_api_mcp.reconcile import reconcile


def test_sibling_commit_on_other_branch_no_longer_false_positives():
    # Old behaviour (documented in the T2 plan): a sibling child of `p` on
    # ANOTHER branch made the walk return landed. The branch head says the
    # write did NOT land — that must win, and the walk must not run at all.
    get_commits = MagicMock()
    got = reconcile(get_commits, previous_commit="p", resolve_head=lambda: "p")
    assert got["outcome"] == "not_landed"
    assert got["commit_id"] is None
    get_commits.assert_not_called()                 # verdict is head-only


def test_branch_head_advanced_means_landed_with_that_commit():
    got = reconcile(MagicMock(), previous_commit="p", resolve_head=lambda: "c2")
    assert got["outcome"] == "landed"
    assert got["commit_id"] == "c2"
    assert got["observed_version"] == "c2" and got["expected_version"] == "p"


def test_resolver_error_is_indeterminate():
    def boom():
        raise TimeoutError("network")
    got = reconcile(MagicMock(), previous_commit="p", resolve_head=boom)
    assert got["outcome"] == "indeterminate"
    assert got["expected_version"] == "p" and got["commit_id"] is None


def test_legacy_walk_still_works_without_resolver():
    commits = [{"@id": "c2", "previousCommit": {"@id": "p"}},
               {"@id": "p", "previousCommit": None}]
    got = reconcile(lambda: commits, previous_commit="p")
    assert got["outcome"] == "landed" and got["commit_id"] == "c2"


def test_first_commit_on_branch_with_no_landed_commits_yet_is_not_landed():
    got = reconcile(MagicMock(), previous_commit=None, resolve_head=lambda: None)
    assert got["outcome"] == "not_landed"
    assert got["commit_id"] is None
