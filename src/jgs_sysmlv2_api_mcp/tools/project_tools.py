# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""T3 — project lifecycle tool logic.

The pilot 500s minimal PUT bodies and only accepts a full readback echo
(tool-catalog spike ground truth 18), and its DELETE answers 500 even on
success (GT 19) — so update is GET-echo-modify-PUT and delete is
fire-then-verify. D9: the session's configured project is never deletable."""


def update_project_fields(api_client, project_id=None, name=None, description=None):
    """GET-echo-modify-PUT, then return a fresh verified readback."""
    echo = api_client.get_project(project_id)
    if name is not None:
        echo["name"] = name
    if description is not None:
        echo["description"] = description
    api_client.put_project(echo["@id"], echo)
    return api_client.get_project(echo["@id"])


def delete_project_verified(api_client, project_id, configured_project):
    """Refuse the session's configured project client-side (D9 — deleting it
    bricks every later tool call), fire the DELETE, then VERIFY via the
    project list because the pilot's status code means nothing (GT 19)."""
    if project_id == configured_project:
        return {"deleted": False,
                "reason": "refusing to delete the session's configured project"}
    api_client.delete_project(project_id)
    remaining = {p["@id"] for p in api_client.list_projects()}
    return {"deleted": project_id not in remaining}
