# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""Task 1 — Day-one write spike (SERIAL GATE). RESULT: PASS (2026-07-02).

Validates the highest-risk assumption before any tool is built: can we POST a
client-UUID, multi-DataVersion commit (PartDefinition + its OwningMembership) to
the OMG pilot and read it back with the client-supplied ids AND full fidelity?

GROUND TRUTH discovered by this spike (all fed back into the plan/spec):
  1. The POST body is a *CommitRequest*, not a Commit — NO top-level @id; the
     SERVER assigns the commit id. Each change is a DataVersionRequest whose
     `payload` is required and whose `identity` is {@id, @type: "DataIdentity"}.
  2. The official generated client's TYPED Element model only exposes id/type/
     identifier — it SILENTLY DROPS declaredName and all SysML payload fields,
     even in to_dict(). So reads MUST use the raw-JSON path
     (client.call_api(..., _preload_content=False)), not typed models.
  3. Because the client cannot supply the Commit @id, the ambiguous-write
     reconcile (plan Task 9) must key on branch head-advance, NOT a client
     commit id — build_commit_body must not mint/embed a client Commit @id.

Requires a live pilot at $SYSMLV2_HOST (default http://localhost:9000).
Run: pytest tests/test_spike_write_roundtrip.py -v -m integration
"""
import json
import os
import uuid
import pytest

HOST = os.environ.get("SYSMLV2_HOST", "http://localhost:9000")


def _raw_get(client, path):
    """GET raw JSON through the official client's plumbing WITHOUT typed
    deserialization (which loses SysML payload fields — ground-truth #2)."""
    resp = client.call_api(path, "GET", response_type=None, _preload_content=False)
    data = resp.data if hasattr(resp, "data") else resp[0].data
    return json.loads(data.decode())


@pytest.mark.integration
def test_client_uuid_multi_dataversion_roundtrip():
    import sysml_v2_api_client as sc
    from sysml_v2_api_client.api.project_api import ProjectApi
    from sysml_v2_api_client.api.commit_api import CommitApi

    client = sc.ApiClient(sc.Configuration(host=HOST))
    project_api, commit_api = ProjectApi(client), CommitApi(client)

    # 1. create a project (typed call is fine here — id/name survive)
    proj = project_api.post_project(body={"@type": "Project", "name": f"spike-{uuid.uuid4().hex[:8]}"})
    pid = proj.id
    assert pid, f"no project id: {proj}"

    # 2. client-minted UUIDs; POST a CommitRequest (no top-level @id)
    part_id, mem_id = str(uuid.uuid4()), str(uuid.uuid4())
    commit_request = {
        "@type": "Commit",
        "change": [
            {"@type": "DataVersion",
             "payload": {"@id": part_id, "@type": "PartDefinition", "declaredName": "Vehicle"},
             "identity": {"@id": part_id, "@type": "DataIdentity"}},
            {"@type": "DataVersion",
             "payload": {"@id": mem_id, "@type": "OwningMembership",
                         "ownedMemberElement": {"@id": part_id}},
             "identity": {"@id": mem_id, "@type": "DataIdentity"}},
        ],
    }
    commit = commit_api.post_commit_by_project(pid, body=commit_request)
    commit_id = commit.id                       # SERVER-assigned
    assert commit_id, f"no commit id: {commit}"

    # 3. read the element back via the RAW path (full fidelity)
    got = _raw_get(client, f"/projects/{pid}/commits/{commit_id}/elements/{part_id}")

    # 4. fidelity relation (spec §6): client UUID preserved + type + declared name
    assert got["@id"] == part_id, f"pilot did not honor client element UUID: {got.get('@id')}"
    assert got["@type"] == "PartDefinition"
    assert got["declaredName"] == "Vehicle"

    # 5. the synthesized OwningMembership also round-trips and links to the part
    mem = _raw_get(client, f"/projects/{pid}/commits/{commit_id}/elements/{mem_id}")
    assert mem["@id"] == mem_id
    assert mem["@type"] == "OwningMembership"
    assert mem["ownedMemberElement"]["@id"] == part_id   # ownership preserved
