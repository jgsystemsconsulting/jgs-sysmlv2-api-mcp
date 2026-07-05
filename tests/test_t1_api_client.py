# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""T1 tests — ApiClient navigation-read extensions.

Same mock-transport pattern as test_api_client.py: bypass __init__, stub
_raw.call_api, assert raw-JSON path + exact URL construction."""
from unittest.mock import MagicMock

from jgs_sysmlv2_api_mcp.api_client import ApiClient


class _Resp:
    def __init__(self, data_bytes):
        self.data = data_bytes


def _make(project="p"):
    ac = ApiClient.__new__(ApiClient)      # bypass __init__ network wiring
    ac._project = project
    ac._raw = MagicMock()
    return ac


def test_get_element_project_override_changes_path():
    ac = _make(project="default")
    ac._raw.call_api.return_value = _Resp(b'{"@id":"x"}')
    ac.get_element("c1", "x", project="other")
    assert ac._raw.call_api.call_args[0][0] == "/projects/other/commits/c1/elements/x"


def test_get_element_without_override_uses_configured_project():
    ac = _make(project="default")
    ac._raw.call_api.return_value = _Resp(b'{"@id":"x"}')
    ac.get_element("c1", "x")
    assert ac._raw.call_api.call_args[0][0] == "/projects/default/commits/c1/elements/x"


def test_resolve_head_finds_the_commit_nobody_parents():
    """Bug fix: the pilot's commit list is NOT reliably newest-first for
    rapid successive commits (confirmed empirically: 5/8 trials wrong). Head
    is the one commit that is nobody's previousCommit, regardless of list
    order — proven here by putting the actual head FIRST in the wrong slot
    relative to created-time-implied order to show list position is ignored."""
    ac = _make()
    ac._raw.call_api.return_value = _Resp(
        b'[{"@id":"older","previousCommit":null},'
        b'{"@id":"newest","previousCommit":{"@id":"older"}}]')
    assert ac.resolve_head() == "newest"


def test_resolve_head_ignores_list_order_when_older_commit_listed_first():
    """Same fact as above, with list order deliberately inverted (the buggy
    pilot behavior this fix targets) — parentage must still win."""
    ac = _make()
    ac._raw.call_api.return_value = _Resp(
        b'[{"@id":"newest","previousCommit":{"@id":"older"}},'
        b'{"@id":"older","previousCommit":null}]')
    assert ac.resolve_head() == "newest"


def test_resolve_head_falls_back_to_list_order_when_ambiguous():
    """0 or 2+ parentless commits (e.g. multiple branches, not a T1 scenario)
    falls back to the old list-order behaviour rather than raising."""
    ac = _make()
    ac._raw.call_api.return_value = _Resp(
        b'[{"@id":"newest","previousCommit":null},'
        b'{"@id":"older","previousCommit":null}]')
    assert ac.resolve_head() == "newest"


def test_resolve_head_single_commit_no_previousCommit():
    """The most common real call: first read after a project's only commit.
    previousCommit is null/absent -> the single commit is nobody's child but
    still correctly identified as head (it's the only candidate)."""
    ac = _make()
    ac._raw.call_api.return_value = _Resp(b'[{"@id":"only","previousCommit":null}]')
    assert ac.resolve_head() == "only"


def test_resolve_head_empty_history_returns_none():
    ac = _make()
    ac._raw.call_api.return_value = _Resp(b'[]')
    assert ac.resolve_head() is None


def test_query_uses_project_scoped_path_with_commitId_param():
    """Pre-existing v0 bug fix (ground truth 9): the endpoint is project-scoped
    with commitId as a query param, not /commits/{c}/query-results (404s live)."""
    ac = _make(project="p")
    ac._raw.call_api.return_value = _Resp(b'[]')
    ac.query("c1", {"@type": "Query", "select": []})
    args, kwargs = ac._raw.call_api.call_args
    assert args[0] == "/projects/p/query-results"
    assert kwargs["query_params"] == [("commitId", "c1")]


def test_query_fills_required_name_field_if_missing():
    ac = _make(project="p")
    ac._raw.call_api.return_value = _Resp(b'[]')
    ac.query("c1", {"@type": "Query", "select": []})
    assert ac._raw.call_api.call_args[1]["body"]["name"]


def test_get_project_path():
    ac = _make(project="p")
    ac._raw.call_api.return_value = _Resp(b'{"@id":"p","defaultBranch":{"@id":"b"}}')
    got = ac.get_project()
    assert got["defaultBranch"]["@id"] == "b"
    assert ac._raw.call_api.call_args[0][0] == "/projects/p"


def test_get_roots_path():
    ac = _make(project="p")
    ac._raw.call_api.return_value = _Resp(b'[{"@id":"r1"}]')
    assert ac.get_roots("c1")[0]["@id"] == "r1"
    assert ac._raw.call_api.call_args[0][0] == "/projects/p/commits/c1/roots"


def test_get_relationships_path_and_direction():
    ac = _make(project="p")
    ac._raw.call_api.return_value = _Resp(b'[]')
    ac.get_relationships("c1", "e1", direction="in")
    args, kwargs = ac._raw.call_api.call_args
    assert args[0] == "/projects/p/commits/c1/elements/e1/relationships"
    assert kwargs["query_params"] == [("direction", "in")]


def test_get_relationships_default_direction_both():
    ac = _make(project="p")
    ac._raw.call_api.return_value = _Resp(b'[]')
    ac.get_relationships("c1", "e1")
    assert ac._raw.call_api.call_args[1]["query_params"] == [("direction", "both")]


def test_get_commit_path():
    ac = _make(project="p")
    ac._raw.call_api.return_value = _Resp(b'{"@id":"c1"}')
    assert ac.get_commit("c1")["@id"] == "c1"
    assert ac._raw.call_api.call_args[0][0] == "/projects/p/commits/c1"


def test_get_commit_changes_path():
    ac = _make(project="p")
    ac._raw.call_api.return_value = _Resp(b'[{"@type":"DataVersion"}]')
    assert ac.get_commit_changes("c1")[0]["@type"] == "DataVersion"
    assert ac._raw.call_api.call_args[0][0] == "/projects/p/commits/c1/changes"
