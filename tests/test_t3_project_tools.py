# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""T3 tests — project update/delete tool logic."""
from unittest.mock import MagicMock

from jgs_sysmlv2_api_mcp.tools.project_tools import (
    delete_project_verified,
    update_project_fields,
)


def test_update_sends_full_echo_with_edits():
    api = MagicMock()
    echo = {"@id": "x", "@type": "Project", "name": "old", "description": "d0",
            "created": "2026-07-02T00:00:00Z", "defaultBranch": {"@id": "b"},
            "alias": ["old"]}
    updated = dict(echo, name="new")
    api.get_project.side_effect = [dict(echo), updated]     # pre-echo, post-verify
    got = update_project_fields(api, project_id="x", name="new")
    body = api.put_project.call_args[0][1]
    assert api.put_project.call_args[0][0] == "x"
    assert body["name"] == "new"
    assert body["description"] == "d0"                      # untouched field kept
    assert body["defaultBranch"] == {"@id": "b"}            # echo fields preserved (GT 18)
    assert got["name"] == "new"                             # returns the VERIFIED readback


def test_update_touches_only_provided_fields():
    api = MagicMock()
    echo = {"@id": "x", "@type": "Project", "name": "keep", "description": "d0"}
    api.get_project.side_effect = [dict(echo), dict(echo, description="d1")]
    update_project_fields(api, description="d1")            # project_id defaults (D1)
    body = api.put_project.call_args[0][1]
    assert body["name"] == "keep" and body["description"] == "d1"


def test_delete_refuses_configured_project_before_any_network_call():
    api = MagicMock()
    got = delete_project_verified(api, "cfgproj", configured_project="cfgproj")
    assert got["deleted"] is False and "configured" in got["reason"]
    api.delete_project.assert_not_called()                  # D9: refused client-side


def test_delete_fires_then_verifies_via_list():
    api = MagicMock()
    api.list_projects.return_value = [{"@id": "other"}]
    got = delete_project_verified(api, "victim", configured_project="cfgproj")
    api.delete_project.assert_called_once_with("victim")
    assert got == {"deleted": True}
    # still listed afterwards -> deletion did NOT take effect (GT 19 verify-after)
    api.list_projects.return_value = [{"@id": "victim"}]
    assert delete_project_verified(api, "victim", "cfgproj") == {"deleted": False}
