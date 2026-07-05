# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""T3 tests — ApiClient project-lifecycle wrappers (mock transport)."""
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


def test_create_project_body_with_description():
    ac = _make()
    ac._raw.call_api.return_value = _Resp(b'{"@id":"new"}')
    ac.create_project("proj", "desc")
    args, kwargs = ac._raw.call_api.call_args
    assert args[:2] == ("/projects", "POST")
    assert kwargs["body"] == {"@type": "Project", "name": "proj", "description": "desc"}


def test_create_project_omits_absent_description():
    ac = _make()
    ac._raw.call_api.return_value = _Resp(b'{"@id":"new"}')
    ac.create_project("proj")
    assert ac._raw.call_api.call_args[1]["body"] == {"@type": "Project", "name": "proj"}


def test_put_project_sends_body_to_project_path():
    ac = _make()
    ac._raw.call_api.return_value = _Resp(b'{"@id":"x","name":"renamed"}')
    got = ac.put_project("x", {"@id": "x", "@type": "Project", "name": "renamed"})
    assert got["name"] == "renamed"
    args, kwargs = ac._raw.call_api.call_args
    assert args[:2] == ("/projects/x", "PUT")
    assert kwargs["body"]["name"] == "renamed"


def test_delete_project_swallows_api_exception():
    from sysml_v2_api_client.rest import ApiException
    ac = _make()
    # ground truth 19: the pilot answers 500 even when the delete succeeded
    ac._raw.call_api.side_effect = ApiException(status=500, reason="lies")
    ac.delete_project("x")                 # must NOT raise
    assert ac._raw.call_api.call_args[0][:2] == ("/projects/x", "DELETE")
