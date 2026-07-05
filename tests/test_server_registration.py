# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
from jgs_sysmlv2_api_mcp.api_client import AmbiguousWrite, ApiClient, CommitConflict
from jgs_sysmlv2_api_mcp import server as server_module
from jgs_sysmlv2_api_mcp.server import build_server


def test_all_expected_tools_registered(monkeypatch):
    monkeypatch.setenv("SYSMLV2_BASE_URL", "http://localhost:9000")
    monkeypatch.setenv("SYSMLV2_TOKEN", "t")
    monkeypatch.setenv("SYSMLV2_PROJECT", "p")
    server = build_server()
    names = set(server.tool_names())     # helper exposing registered tool names
    expected = {"list_projects", "get_commits", "get_element", "query_elements",
                "create_element", "modify_element", "delete_element", "delete_subtree",
                "review_changes", "commit_changes", "discard_changes",
                "ping", "stats", "nav_traverse",
                # T1 navigation reads
                "get_project", "get_root_elements", "get_relationships",
                "get_children", "find_by_name", "get_commit",
                "get_commit_changes", "diff_commits",
                # T2 versioning lifecycle
                "list_branches", "create_branch", "delete_branch", "merge_branch",
                "set_branch", "list_tags", "create_tag",
                # T3 project lifecycle
                "create_project", "update_project", "delete_project",
                # T4 authoring extensions
                "create_relationship", "move_element", "stage_batch",
                # licence visibility (always-available FREE tool)
                "get_licence"}
    assert expected <= names
    assert len(names) == 36


def test_get_element_uses_explicit_commit_id_without_calling_resolve_head(monkeypatch):
    """Old callers who pass commit_id explicitly must see byte-identical
    behavior — resolve_head must never be consulted."""
    monkeypatch.setenv("SYSMLV2_BASE_URL", "http://localhost:9000")
    monkeypatch.setenv("SYSMLV2_TOKEN", "t")
    monkeypatch.setenv("SYSMLV2_PROJECT", "p")
    calls = []
    monkeypatch.setattr(ApiClient, "resolve_head", lambda self, project=None, branch_id=None: calls.append("resolve_head") or "should-not-be-used")
    monkeypatch.setattr(ApiClient, "get_element", lambda self, commit_id, element_id, project=None: {"@id": element_id, "commit_id": commit_id})
    server = build_server()
    handler = server._tools["get_element"]["handler"]
    result = handler({"commit_id": "c1", "element_id": "e1"})
    assert result == {"@id": "e1", "commit_id": "c1"}
    assert calls == []


def test_get_element_without_commit_id_defaults_to_resolve_head(monkeypatch):
    """New callers who omit commit_id must get the branch head via
    api.resolve_head() (D2)."""
    monkeypatch.setenv("SYSMLV2_BASE_URL", "http://localhost:9000")
    monkeypatch.setenv("SYSMLV2_TOKEN", "t")
    monkeypatch.setenv("SYSMLV2_PROJECT", "p")
    monkeypatch.setenv("SYSMLV2_BRANCH", "b1")   # avoid _active_branch_id() hitting get_project()
    calls = []
    monkeypatch.setattr(ApiClient, "resolve_head", lambda self, project=None, branch_id=None: calls.append("resolve_head") or "head-commit")
    monkeypatch.setattr(ApiClient, "get_element", lambda self, commit_id, element_id, project=None: {"@id": element_id, "commit_id": commit_id})
    server = build_server()
    handler = server._tools["get_element"]["handler"]
    result = handler({"element_id": "e1"})
    assert result == {"@id": "e1", "commit_id": "head-commit"}
    assert calls == ["resolve_head"]


def test_get_element_without_commit_id_raises_on_empty_project(monkeypatch):
    monkeypatch.setenv("SYSMLV2_BASE_URL", "http://localhost:9000")
    monkeypatch.setenv("SYSMLV2_TOKEN", "t")
    monkeypatch.setenv("SYSMLV2_PROJECT", "p")
    monkeypatch.setenv("SYSMLV2_BRANCH", "b1")   # avoid _active_branch_id() hitting get_project()
    monkeypatch.setattr(ApiClient, "resolve_head", lambda self, project=None, branch_id=None: None)
    server = build_server()
    handler = server._tools["get_element"]["handler"]
    try:
        handler({"element_id": "e1"})
        assert False, "expected ValueError"
    except ValueError as e:
        assert "no commits yet" in str(e)


def test_delete_branch_requires_confirm_true_missing_key(monkeypatch):
    monkeypatch.setenv("SYSMLV2_BASE_URL", "http://localhost:9000")
    monkeypatch.setenv("SYSMLV2_TOKEN", "t")
    monkeypatch.setenv("SYSMLV2_PROJECT", "p")
    server = build_server()
    handler = server._tools["delete_branch"]["handler"]
    try:
        handler({"branch_id": "b1"})
        assert False, "expected ValueError"
    except ValueError as e:
        assert "delete_branch is destructive; pass confirm: true" in str(e)


def test_delete_branch_requires_confirm_true_explicit_false(monkeypatch):
    monkeypatch.setenv("SYSMLV2_BASE_URL", "http://localhost:9000")
    monkeypatch.setenv("SYSMLV2_TOKEN", "t")
    monkeypatch.setenv("SYSMLV2_PROJECT", "p")
    server = build_server()
    handler = server._tools["delete_branch"]["handler"]
    try:
        handler({"branch_id": "b1", "confirm": False})
        assert False, "expected ValueError"
    except ValueError as e:
        assert "delete_branch is destructive; pass confirm: true" in str(e)


def test_delete_branch_confirm_true_calls_delete_branch_verified(monkeypatch):
    monkeypatch.setenv("SYSMLV2_BASE_URL", "http://localhost:9000")
    monkeypatch.setenv("SYSMLV2_TOKEN", "t")
    monkeypatch.setenv("SYSMLV2_PROJECT", "p")
    calls = []
    monkeypatch.setattr(server_module, "delete_branch_verified",
                        lambda api, branch_id: calls.append((api, branch_id)) or {"deleted": True})
    server = build_server()
    handler = server._tools["delete_branch"]["handler"]
    result = handler({"branch_id": "b1", "confirm": True})
    assert result == {"deleted": True}
    assert len(calls) == 1
    assert calls[0][1] == "b1"


def test_merge_branch_requires_confirm_true_missing_key(monkeypatch):
    monkeypatch.setenv("SYSMLV2_BASE_URL", "http://localhost:9000")
    monkeypatch.setenv("SYSMLV2_TOKEN", "t")
    monkeypatch.setenv("SYSMLV2_PROJECT", "p")
    server = build_server()
    handler = server._tools["merge_branch"]["handler"]
    try:
        handler({"source_branch_id": "s1", "target_branch_id": "t1"})
        assert False, "expected ValueError"
    except ValueError as e:
        assert "merge_branch writes to the target branch; pass confirm: true" in str(e)


def test_merge_branch_requires_confirm_true_explicit_false(monkeypatch):
    monkeypatch.setenv("SYSMLV2_BASE_URL", "http://localhost:9000")
    monkeypatch.setenv("SYSMLV2_TOKEN", "t")
    monkeypatch.setenv("SYSMLV2_PROJECT", "p")
    server = build_server()
    handler = server._tools["merge_branch"]["handler"]
    try:
        handler({"source_branch_id": "s1", "target_branch_id": "t1", "confirm": False})
        assert False, "expected ValueError"
    except ValueError as e:
        assert "merge_branch writes to the target branch; pass confirm: true" in str(e)


def test_merge_branch_confirm_true_calls_squash_merge(monkeypatch):
    monkeypatch.setenv("SYSMLV2_BASE_URL", "http://localhost:9000")
    monkeypatch.setenv("SYSMLV2_TOKEN", "t")
    monkeypatch.setenv("SYSMLV2_PROJECT", "p")
    calls = []

    def fake_squash_merge(api, source_branch_id, target_branch_id, description=None):
        calls.append((source_branch_id, target_branch_id, description))
        return {"outcome": "merged"}

    monkeypatch.setattr(server_module, "squash_merge", fake_squash_merge)
    server = build_server()
    handler = server._tools["merge_branch"]["handler"]
    result = handler({"source_branch_id": "s1", "target_branch_id": "t1", "confirm": True})
    assert result == {"outcome": "merged"}
    assert calls == [("s1", "t1", None)]


def test_merge_branch_translates_commit_conflict(monkeypatch):
    monkeypatch.setenv("SYSMLV2_BASE_URL", "http://localhost:9000")
    monkeypatch.setenv("SYSMLV2_TOKEN", "t")
    monkeypatch.setenv("SYSMLV2_PROJECT", "p")

    def raise_conflict(api, source_branch_id, target_branch_id, description=None):
        raise CommitConflict("target branch head advanced")

    monkeypatch.setattr(server_module, "squash_merge", raise_conflict)
    server = build_server()
    handler = server._tools["merge_branch"]["handler"]
    result = handler({"source_branch_id": "s1", "target_branch_id": "t1", "confirm": True})
    assert result == {"outcome": "conflict",
                      "hint": "target branch head advanced; re-run merge_branch"}


def test_merge_branch_translates_ambiguous_write(monkeypatch):
    monkeypatch.setenv("SYSMLV2_BASE_URL", "http://localhost:9000")
    monkeypatch.setenv("SYSMLV2_TOKEN", "t")
    monkeypatch.setenv("SYSMLV2_PROJECT", "p")

    def raise_ambiguous(api, source_branch_id, target_branch_id, description=None):
        raise AmbiguousWrite("connection dropped after send")

    monkeypatch.setattr(server_module, "squash_merge", raise_ambiguous)
    server = build_server()
    handler = server._tools["merge_branch"]["handler"]
    result = handler({"source_branch_id": "s1", "target_branch_id": "t1", "confirm": True})
    assert result == {"outcome": "error",
                      "reason": "merge commit response lost after send; verify target branch head before retrying"}


def test_nav_traverse_follows_relationships_and_includes_names(monkeypatch):
    """nav_traverse's follow_relationships + include_names args (T4) have no
    dedicated coverage anywhere — only tool registration is checked. This
    proves both are wired into the real handler: `target1` is reachable from
    `root1` ONLY via an outgoing typed relationship (root1 -> target1), never
    via containment (root1's ownedMember is just child1), so a plain
    containment-only traversal cannot find it. Also proves the include_names
    fallback (`declaredName` preferred over `name`) by giving `target1` only
    a bare `name` field and no `declaredName` at all.
    """
    monkeypatch.setenv("SYSMLV2_BASE_URL", "http://localhost:9000")
    monkeypatch.setenv("SYSMLV2_TOKEN", "t")
    monkeypatch.setenv("SYSMLV2_PROJECT", "p")
    monkeypatch.setenv("SYSMLV2_BRANCH", "b1")   # avoid _active_branch_id() hitting get_project()

    elements = {
        "root1": {"@id": "root1", "@type": "PartDefinition", "declaredName": "Root",
                  "ownedMember": [{"@id": "child1"}]},
        "child1": {"@id": "child1", "@type": "PartDefinition", "declaredName": "Child"},
        # no declaredName here -> must fall back to "name"
        "target1": {"@id": "target1", "@type": "PartDefinition", "name": "Target"},
    }
    relationships = {
        "root1": [{"@id": "rel1", "@type": "Dependency",
                   "target": [{"@id": "target1"}]}],
        "child1": [],
        "target1": [],
    }

    def fake_get_element(self, commit_id, element_id, project=None):
        return elements[element_id]

    def fake_get_elements(self, commit_id, project=None):
        # child1/target1 have no "ownedMember" key, so child_ids() falls
        # through to this OwningMembership scan; no elements match.
        return []

    def fake_get_relationships(self, commit_id, element_id, direction="both", project=None):
        assert direction == "out"
        return relationships.get(element_id, [])

    monkeypatch.setattr(ApiClient, "get_element", fake_get_element)
    monkeypatch.setattr(ApiClient, "get_elements", fake_get_elements)
    monkeypatch.setattr(ApiClient, "get_relationships", fake_get_relationships)

    server = build_server()
    handler = server._tools["nav_traverse"]["handler"]

    # Containment-only traversal must NOT reach target1.
    contain_only = handler({"commit_id": "c1", "root": "root1"})
    assert "target1" not in contain_only["visited"]

    # follow_relationships=True must reach target1 via the relationship edge.
    result = handler({"commit_id": "c1", "root": "root1", "follow_relationships": True,
                      "include_names": True})
    assert "target1" in result["visited"]
    assert result["elements"]["target1"] == {"name": "Target", "type": "PartDefinition"}
    assert result["elements"]["root1"] == {"name": "Root", "type": "PartDefinition"}


def test_commit_changes_ambiguous_write_uses_branch_authoritative_reconcile(monkeypatch):
    """commit_changes' AmbiguousWrite handler passes
    resolve_head=lambda: api.resolve_head(branch_id=_active_branch_id()) into
    reconcile() (T3, fixing T2's project-wide-walk false positive on a
    sibling branch commit — see reconcile.py). Prove the wiring actually
    fires and takes the branch-authoritative path, not the legacy
    get_commits() walk: resolve_head is stubbed to return a DIFFERENT head
    on its second call (made from inside the reconcile lambda) than on its
    first call (made before post_commit, to seed `previous_commit`) — so a
    correct branch-authoritative reconcile must report "landed" with the
    NEW head as commit_id. get_commits is stubbed to return data engineered
    so the legacy project-wide walk would find NO child of previous_commit
    and report "not_landed" instead — if reconcile ever fell back to the
    legacy walk (old buggy behavior, or a broken lambda), the verdict would
    flip to "not_landed" and this assertion would catch it. get_commits is
    also asserted never called, proving reconcile took the resolver branch
    entirely rather than consulting it at all.
    """
    monkeypatch.setenv("SYSMLV2_BASE_URL", "http://localhost:9000")
    monkeypatch.setenv("SYSMLV2_TOKEN", "t")
    monkeypatch.setenv("SYSMLV2_PROJECT", "p")
    monkeypatch.setenv("SYSMLV2_BRANCH", "b1")   # keep _active_branch_id() on its fast path

    resolve_head_calls = []
    get_commits_calls = []

    def fake_resolve_head(self, project=None, branch_id=None):
        resolve_head_calls.append(branch_id)
        # 1st call: seed `previous_commit` before post_commit.
        # 2nd call: made from inside reconcile's resolve_head lambda.
        return "commit-before" if len(resolve_head_calls) == 1 else "commit-after-on-branch"

    def fake_get_commits(self, project=None):
        get_commits_calls.append(True)
        # Engineered so the LEGACY project-wide walk would find no commit
        # whose previousCommit is "commit-before" (none of these point to
        # it) and would therefore report "not_landed" — the WRONG verdict,
        # since the branch-authoritative resolver above proves it landed.
        return [
            {"@id": "commit-before", "previousCommit": None},
            {"@id": "sibling-branch-commit", "previousCommit": {"@id": "some-other-parent"}},
        ]

    def fake_post_commit(self, commit_body, branch_id=None):
        raise AmbiguousWrite("connection dropped after send")

    monkeypatch.setattr(ApiClient, "resolve_head", fake_resolve_head)
    monkeypatch.setattr(ApiClient, "get_commits", fake_get_commits)
    monkeypatch.setattr(ApiClient, "post_commit", fake_post_commit)

    server = build_server()
    create_handler = server._tools["create_element"]["handler"]
    review_handler = server._tools["review_changes"]["handler"]
    commit_handler = server._tools["commit_changes"]["handler"]

    create_handler({"type": "PartDefinition", "name": "Widget", "owner": "owner-1"})
    reviewed = review_handler({})
    token = reviewed["confirm_token"]

    result = commit_handler({"confirm": token})

    assert result == {
        "outcome": "landed",
        "commit_id": "commit-after-on-branch",
        "observed_version": "commit-after-on-branch",
        "expected_version": "commit-before",
    }
    # both resolve_head calls were branch-scoped (b1), never a bare project-wide lookup
    assert resolve_head_calls == ["b1", "b1"]
    # legacy get_commits walk was never consulted — proves the resolver path was taken
    assert get_commits_calls == []
