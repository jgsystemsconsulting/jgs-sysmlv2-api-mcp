# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""Task 5 tests — api_client wrapper. Reads return RAW JSON (full fidelity);
POST /commits is never auto-retried (SPIKE ground truth 2026-07-02)."""
from unittest.mock import MagicMock

import pytest

from jgs_sysmlv2_api_mcp.api_client import ApiClient, AmbiguousWrite, CommitConflict


class _Resp:
    def __init__(self, data_bytes):
        self.data = data_bytes


def _make(project="p"):
    ac = ApiClient.__new__(ApiClient)      # bypass __init__ network wiring
    ac._project = project
    ac._raw = MagicMock()
    return ac


def test_get_element_returns_raw_json_with_all_fields():
    ac = _make()
    # RAW path: a typed model would drop declaredName; raw JSON keeps it.
    ac._raw.call_api.return_value = _Resp(
        b'{"@id":"x","@type":"PartDefinition","declaredName":"Vehicle"}')
    got = ac.get_element("commit1", "x")
    assert got["@id"] == "x"
    assert got["@type"] == "PartDefinition"
    assert got["declaredName"] == "Vehicle"        # proves raw fidelity
    args, kwargs = ac._raw.call_api.call_args
    assert args[0] == "/projects/p/commits/commit1/elements/x"
    assert args[1] == "GET"
    assert kwargs["_preload_content"] is False
    assert kwargs["response_type"] is None


def test_list_projects_returns_raw_list():
    ac = _make()
    ac._raw.call_api.return_value = _Resp(b'[{"@id":"p1"},{"@id":"p2"}]')
    got = ac.list_projects()
    assert [p["@id"] for p in got] == ["p1", "p2"]
    assert ac._raw.call_api.call_args[0][0] == "/projects"
    assert ac._raw.call_api.call_args[0][1] == "GET"


def test_get_commits_returns_raw_list():
    ac = _make()
    ac._raw.call_api.return_value = _Resp(b'[{"@id":"c1"},{"@id":"c2"}]')
    got = ac.get_commits()
    assert [c["@id"] for c in got] == ["c1", "c2"]
    assert ac._raw.call_api.call_args[0][0] == "/projects/p/commits"


def test_post_commit_not_retried_on_timeout():
    ac = _make()
    ac._raw.call_api.side_effect = TimeoutError("read timeout")
    with pytest.raises(AmbiguousWrite):
        ac.post_commit({"@type": "Commit", "change": []})
    assert ac._raw.call_api.call_count == 1        # NOT retried


def test_post_commit_409_raises_commit_conflict():
    from sysml_v2_api_client.rest import ApiException
    ac = _make()
    ac._raw.call_api.side_effect = ApiException(status=409, reason="Conflict")
    with pytest.raises(CommitConflict):
        ac.post_commit({"@type": "Commit", "change": []})
    assert ac._raw.call_api.call_count == 1


def test_post_commit_reraises_other_api_exceptions():
    from sysml_v2_api_client.rest import ApiException
    ac = _make()
    ac._raw.call_api.side_effect = ApiException(status=400, reason="Bad Request")
    with pytest.raises(ApiException):
        ac.post_commit({"@type": "Commit", "change": []})
