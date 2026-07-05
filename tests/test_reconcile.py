# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""Task 9 — ambiguous-write reconciliation (spec §5).

SPIKE CORRECTION applied: the pilot's POST body is a CommitRequest with NO
top-level @id (the server assigns the commit id — see SPIKE RESULT + ground
truth #3 in tests/test_spike_write_roundtrip.py). Because the client cannot
supply a commit id up front, reconcile() cannot key on a client-minted id.
Instead it keys on BRANCH HEAD-ADVANCE: compare the branch head before
(previous_commit) and after (get_commits()) — if the head moved past
previous_commit, the write landed.

Bug fix (found during T1 implementation, see reconcile.py): get_commits()
does NOT reliably return commits newest-first for rapid successive commits —
head is found via previousCommit-chain parentage instead, falling back to
commits[0] only when previous_commit is None (first-ever commit) or
previousCommit data is unavailable on the commit representation.
"""
from jgs_sysmlv2_api_mcp.reconcile import reconcile


def test_reconcile_landed_when_head_advances_past_previous_commit():
    # after an ambiguous write, the head is a NEW commit that isn't previous_commit
    committed = [{"@id": "c-new"}, {"@id": "c-old"}]
    r = reconcile(get_commits=lambda: committed, previous_commit="c-old")
    assert r["outcome"] == "landed"
    assert r["commit_id"] == "c-new"
    assert r["observed_version"] == "c-new"
    assert r["expected_version"] == "c-old"


def test_reconcile_landed_on_first_ever_commit_with_no_previous():
    # previous_commit=None (first commit on a fresh branch) + any head -> landed
    committed = [{"@id": "c-first"}]
    r = reconcile(get_commits=lambda: committed, previous_commit=None)
    assert r["outcome"] == "landed"
    assert r["commit_id"] == "c-first"
    assert r["observed_version"] == "c-first"
    assert r["expected_version"] is None


def test_reconcile_not_landed_when_head_unchanged():
    # head is STILL previous_commit -> the write did not land
    committed = [{"@id": "c-old"}]
    r = reconcile(get_commits=lambda: committed, previous_commit="c-old")
    assert r["outcome"] == "not_landed"
    assert r["commit_id"] is None
    assert r["observed_version"] == "c-old"
    assert r["expected_version"] == "c-old"


def test_reconcile_not_landed_when_no_commits_and_previous_expected():
    # empty commit list but caller expected a prior head -> not landed, not a crash
    r = reconcile(get_commits=lambda: [], previous_commit="c-old")
    assert r["outcome"] == "not_landed"
    assert r["observed_version"] is None
    assert r["expected_version"] == "c-old"


def test_reconcile_read_fails_is_indeterminate():
    def boom():
        raise TimeoutError()

    r = reconcile(get_commits=boom, previous_commit="c-old")
    assert r["outcome"] == "indeterminate"
    assert r["commit_id"] is None
    assert r["observed_version"] is None
    assert r["expected_version"] == "c-old"   # caller knows what head it was waiting past
    assert "hint" in r and r["hint"]


def test_reconcile_accepts_object_commits_with_id_attribute():
    # get_commits() may return typed objects (e.g. official client models) with .id,
    # not just dicts — mirrors CommitApi's typed responses.
    class Commit:
        def __init__(self, id_):
            self.id = id_

    committed = [Commit("c-new"), Commit("c-old")]
    r = reconcile(get_commits=lambda: committed, previous_commit="c-old")
    assert r["outcome"] == "landed"
    assert r["commit_id"] == "c-new"


def test_reconcile_ignores_list_order_finds_head_by_previousCommit():
    """Bug fix: the pilot's commit list is NOT reliably newest-first for
    rapid successive commits (same root cause as ApiClient.resolve_head).
    List order is deliberately inverted here (the buggy pilot behavior this
    fix targets) — reconcile must still find "c-new" as the landed commit by
    matching previousCommit to previous_commit, not by trusting position 0."""
    committed = [{"@id": "c-old", "previousCommit": None},
                 {"@id": "c-new", "previousCommit": {"@id": "c-old"}}]
    r = reconcile(get_commits=lambda: committed, previous_commit="c-old")
    assert r["outcome"] == "landed"
    assert r["commit_id"] == "c-new"


def test_reconcile_falls_back_to_list_order_when_previousCommit_ambiguous():
    """Two commits both claim previous_commit as parent (shouldn't happen in
    practice, but reconcile must not crash) -> falls back to commits[0]."""
    committed = [{"@id": "c-a", "previousCommit": {"@id": "c-old"}},
                 {"@id": "c-b", "previousCommit": {"@id": "c-old"}}]
    r = reconcile(get_commits=lambda: committed, previous_commit="c-old")
    assert r["outcome"] == "landed"
    assert r["commit_id"] == "c-a"
