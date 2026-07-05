# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""Ambiguous-write reconciliation (spec §5).

SPIKE CORRECTION (SPIKE RESULT, ground truth #1 and #3 — see
tests/test_spike_write_roundtrip.py): the pilot's POST body is a
CommitRequest with NO top-level @id; the SERVER assigns the commit id.
Because the client never mints a commit id, reconcile() cannot key on a
client-supplied id to find "our" commit after a network failure that leaves
the write's outcome ambiguous (request sent, response lost).

Instead it keys on BRANCH HEAD-ADVANCE: capture the branch head *before* the
ambiguous write as `previous_commit`, then call `get_commits()` afterward and
compare. If the head moved to something other than `previous_commit`, the
write landed (the new head is presumed to be the commit that landed, since a
head-advance only happens as a result of a successful commit). If the head is
still `previous_commit`, the write did not land. If `get_commits()` itself
raises (e.g. network/timeout), the outcome is indeterminate — the caller must
retry the read later using `expected_version` as the head to look past.

BUG FIX (found during T1 implementation, same root cause as
ApiClient.resolve_head): the pilot's commit list is NOT reliably newest-first
for rapid successive commits, so commits[0] cannot be trusted as "the head"
in general. Head-advance detection instead looks for the commit whose
previousCommit is `previous_commit` — i.e. previous_commit's child, which
can only exist if the write landed — falling back to commits[0] (old
behaviour) only when previous_commit is None (first-ever commit; there is no
parent to look for) or when previousCommit data isn't available on the
commit representation (older/synthetic call sites; see _commit_id).
"""


def _commit_id(commit) -> str | None:
    if isinstance(commit, dict):
        return commit.get("@id")
    return getattr(commit, "id", None)


def _previous_commit_id(commit) -> str | None:
    if isinstance(commit, dict):
        return (commit.get("previousCommit") or {}).get("@id")
    prev = getattr(commit, "previous_commit", None) or getattr(commit, "previousCommit", None)
    return getattr(prev, "id", None) if prev is not None else None


def reconcile(get_commits, previous_commit: str | None = None,
              resolve_head=None) -> dict:
    """After an ambiguous POST /commits, decide whether the write landed.

    T3 (branch-scoping fix, T2 debt): when `resolve_head` is provided — a
    callable returning the session branch's CURRENT head id (authoritative
    via GET /branches/{b}) — the verdict keys on that head alone: moved off
    `previous_commit` -> landed (the new head IS the landed commit); still
    `previous_commit` -> not landed; resolver raised -> indeterminate. This
    kills the project-wide walk's false positive: a pre-existing sibling
    commit on ANOTHER branch sharing `previous_commit` as parent (ordinary
    after create_branch) looked like "our" child and produced a bogus
    landed verdict. The legacy walk below remains for call sites without a
    resolver. Relies on the invariant (ground truth 5) that a landed commit
    always advances the branch's head field, so `observed is None` after
    calling the resolver can only mean nothing has landed yet — including on
    a brand-new branch's first-ever commit — never "landed but unreflected."

    Returns the spec §5 structured shape: outcome ("landed" | "not_landed" |
    "indeterminate") + commit_id + observed/expected version, plus a hint
    for the indeterminate case.
    """
    if resolve_head is not None:
        try:
            observed = resolve_head()
        except Exception:
            return {
                "outcome": "indeterminate",
                "commit_id": None,
                "observed_version": None,
                "expected_version": previous_commit,
                "hint": (
                    "re-resolve the session branch head and check whether it has "
                    f"moved past commit @id {previous_commit!r}"
                ),
            }
        if observed is not None and observed != previous_commit:
            return {
                "outcome": "landed",
                "commit_id": observed,
                "observed_version": observed,
                "expected_version": previous_commit,
            }
        return {
            "outcome": "not_landed",
            "commit_id": None,
            "observed_version": observed,
            "expected_version": previous_commit,
        }

    try:
        commits = get_commits()
    except Exception:
        return {
            "outcome": "indeterminate",
            "commit_id": None,
            "observed_version": None,
            "expected_version": previous_commit,
            "hint": (
                "re-run get_commits and check whether the head has moved past "
                f"commit @id {previous_commit!r}"
            ),
        }

    if not commits:
        head_id = None
    elif previous_commit is None:
        # first-ever commit: no parent to look for, list-order is the only signal
        head_id = _commit_id(commits[0])
    else:
        children = [c for c in commits if _previous_commit_id(c) == previous_commit]
        head_id = _commit_id(children[0]) if len(children) == 1 else _commit_id(commits[0])

    if head_id is not None and head_id != previous_commit:
        return {
            "outcome": "landed",
            "commit_id": head_id,
            "observed_version": head_id,
            "expected_version": previous_commit,
        }

    return {
        "outcome": "not_landed",
        "commit_id": None,
        "observed_version": head_id,
        "expected_version": previous_commit,
    }
