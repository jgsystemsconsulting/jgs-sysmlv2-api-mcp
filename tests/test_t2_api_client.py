# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""T2 tests — ApiClient branch/tag methods (mock transport, raw-JSON path)."""
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


def test_get_branches_path():
    ac = _make()
    ac._raw.call_api.return_value = _Resp(b'[{"@id":"b1","name":"main"}]')
    assert ac.get_branches()[0]["@id"] == "b1"
    assert ac._raw.call_api.call_args[0][:2] == ("/projects/p/branches", "GET")


def test_get_branch_path():
    ac = _make()
    ac._raw.call_api.return_value = _Resp(b'{"@id":"b1","head":{"@id":"c9"}}')
    assert ac.get_branch("b1")["head"]["@id"] == "c9"
    assert ac._raw.call_api.call_args[0][0] == "/projects/p/branches/b1"


def test_create_branch_body():
    ac = _make()
    ac._raw.call_api.return_value = _Resp(b'{"@id":"b2"}')
    ac.create_branch("work", "c1")
    args, kwargs = ac._raw.call_api.call_args
    assert args[:2] == ("/projects/p/branches", "POST")
    assert kwargs["body"] == {"@type": "Branch", "name": "work", "head": {"@id": "c1"}}


def test_delete_branch_swallows_api_exception():
    from sysml_v2_api_client.rest import ApiException
    ac = _make()
    # ground truth 11: the pilot answers 500 even when the delete succeeded
    ac._raw.call_api.side_effect = ApiException(status=500, reason="lies")
    ac.delete_branch("b2")                 # must NOT raise
    assert ac._raw.call_api.call_args[0][:2] == ("/projects/p/branches/b2", "DELETE")


def test_get_tags_and_create_tag():
    ac = _make()
    ac._raw.call_api.return_value = _Resp(b'[]')
    ac.get_tags()
    assert ac._raw.call_api.call_args[0][0] == "/projects/p/tags"
    ac._raw.call_api.return_value = _Resp(b'{"@id":"t1"}')
    ac.create_tag("v1.0", "c1")
    args, kwargs = ac._raw.call_api.call_args
    assert args[:2] == ("/projects/p/tags", "POST")
    assert kwargs["body"] == {"@type": "Tag", "name": "v1.0", "taggedCommit": {"@id": "c1"}}


def test_post_commit_targets_branch_via_query_param():
    ac = _make()
    ac._raw.call_api.return_value = _Resp(b'{"@id":"c2"}')
    ac.post_commit({"@type": "Commit", "change": []}, branch_id="b2")
    assert ac._raw.call_api.call_args[1]["query_params"] == [("branchId", "b2")]


def test_post_commit_without_branch_sends_no_query_params():
    ac = _make()
    ac._raw.call_api.return_value = _Resp(b'{"@id":"c2"}')
    ac.post_commit({"@type": "Commit", "change": []})
    assert "query_params" not in ac._raw.call_api.call_args[1]


def test_resolve_head_with_branch_uses_branch_head():
    ac = _make()
    ac._raw.call_api.return_value = _Resp(b'{"@id":"b1","head":{"@id":"c9"}}')
    assert ac.resolve_head(branch_id="b1") == "c9"
    assert ac._raw.call_api.call_args[0][0] == "/projects/p/branches/b1"
