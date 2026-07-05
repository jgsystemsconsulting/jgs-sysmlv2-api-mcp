# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""T2 spike tests — pin the pilot HTTP contract (RESULT: PASS 2026-07-02).

Ground truths encoded (docs/dev/tool-catalog.md "Pilot spike results" 10-15):
tags CRUD shapes, DELETE-returns-500-even-on-success, branch get-by-id head,
prior-less modify/delete versioning, cross-branch net-payload replay, and
verbatim readback-echo recommit. urllib on purpose — pins the HTTP contract
independent of our ApiClient. Requires a live pilot:
  SYSMLV2_HOST=http://localhost:9000 pytest tests/test_spike_t2_endpoints.py -v -m integration
"""
import json
import os
import urllib.error
import urllib.request
import uuid

import pytest

HOST = os.environ.get("SYSMLV2_HOST", "http://localhost:9000")


def _req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(HOST + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as e:
        return e.code, None


def _dv(payload, eid=None):
    return {"@type": "DataVersion", "payload": payload,
            "identity": {"@id": eid or (payload or {}).get("@id"),
                         "@type": "DataIdentity"}}


@pytest.fixture()
def proj():
    """Project with one commit holding element E ("E0")."""
    _, p = _req("POST", "/projects",
                {"@type": "Project", "name": f"t2spike-{uuid.uuid4().hex[:8]}"})
    pid = p["@id"]
    eid = str(uuid.uuid4())
    status, c1 = _req("POST", f"/projects/{pid}/commits", {"@type": "Commit", "change": [
        _dv({"@id": eid, "@type": "PartDefinition", "declaredName": "E0"})]})
    assert status == 200
    return {"pid": pid, "E": eid, "c1": c1["@id"]}


@pytest.mark.integration
def test_tag_create_list_get_and_lying_delete(proj):
    pid = proj["pid"]
    status, tag = _req("POST", f"/projects/{pid}/tags",
                       {"@type": "Tag", "name": "v1.0",
                        "taggedCommit": {"@id": proj["c1"]}})
    assert status == 200                                     # ground truth 10
    assert tag["taggedCommit"]["@id"] == proj["c1"]
    status, tags = _req("GET", f"/projects/{pid}/tags")
    assert status == 200 and len(tags) == 1
    status, one = _req("GET", f"/projects/{pid}/tags/{tag['@id']}")
    assert status == 200
    # ground truth 11: DELETE answers 500 but takes effect
    status, _ = _req("DELETE", f"/projects/{pid}/tags/{tag['@id']}")
    assert status == 500
    _, after = _req("GET", f"/projects/{pid}/tags")
    assert after == []


@pytest.mark.integration
def test_branch_get_by_id_head_and_lying_delete(proj):
    pid = proj["pid"]
    status, br = _req("POST", f"/projects/{pid}/branches",
                      {"@type": "Branch", "name": "spike",
                       "head": {"@id": proj["c1"]}})
    assert status == 200
    status, one = _req("GET", f"/projects/{pid}/branches/{br['@id']}")
    assert status == 200
    assert one["head"]["@id"] == proj["c1"]                  # ground truth 12
    # default branch delete: 500 AND no effect
    _, meta = _req("GET", f"/projects/{pid}")
    default_id = meta["defaultBranch"]["@id"]
    status, _ = _req("DELETE", f"/projects/{pid}/branches/{default_id}")
    assert status == 500
    # non-default delete: 500 BUT effective (ground truth 11)
    status, _ = _req("DELETE", f"/projects/{pid}/branches/{br['@id']}")
    assert status == 500
    _, branches = _req("GET", f"/projects/{pid}/branches")
    ids = {b["@id"] for b in branches}
    assert default_id in ids and br["@id"] not in ids
    # commits survive branch deletion
    status, _ = _req("GET", f"/projects/{pid}/commits/{proj['c1']}")
    assert status == 200


@pytest.mark.integration
def test_priorless_modify_and_delete_version_per_commit(proj):
    pid, E, c1 = proj["pid"], proj["E"], proj["c1"]
    status, c2 = _req("POST", f"/projects/{pid}/commits", {"@type": "Commit", "change": [
        _dv({"@id": E, "@type": "PartDefinition", "declaredName": "E1"})],
        "previousCommit": {"@id": c1}})
    assert status == 200                                     # ground truth 13
    _, at_c2 = _req("GET", f"/projects/{pid}/commits/{c2['@id']}/elements/{E}")
    _, at_c1 = _req("GET", f"/projects/{pid}/commits/{c1}/elements/{E}")
    assert at_c2["declaredName"] == "E1" and at_c1["declaredName"] == "E0"
    # prior-less delete via payload null
    status, c3 = _req("POST", f"/projects/{pid}/commits", {"@type": "Commit", "change": [
        _dv(None, eid=E)], "previousCommit": {"@id": c2["@id"]}})
    assert status == 200
    status, _ = _req("GET", f"/projects/{pid}/commits/{c3['@id']}/elements/{E}")
    assert status == 404
    _, still = _req("GET", f"/projects/{pid}/commits/{c2['@id']}/elements/{E}")
    assert still["declaredName"] == "E1"                     # history intact


@pytest.mark.integration
def test_cross_branch_net_payload_replay(proj):
    pid, E, c1 = proj["pid"], proj["E"], proj["c1"]
    _, br = _req("POST", f"/projects/{pid}/branches",
                 {"@type": "Branch", "name": "work", "head": {"@id": c1}})
    F = str(uuid.uuid4())
    status, bc = _req("POST", f"/projects/{pid}/commits?branchId={br['@id']}",
                      {"@type": "Commit", "change": [
                          _dv({"@id": F, "@type": "PartDefinition", "declaredName": "F"}),
                          _dv({"@id": E, "@type": "PartDefinition", "declaredName": "E-branch"})]})
    assert status == 200
    # replay the SAME @ids onto the default branch (ground truth 14)
    status, mc = _req("POST", f"/projects/{pid}/commits",
                      {"@type": "Commit", "change": [
                          _dv({"@id": F, "@type": "PartDefinition", "declaredName": "F"}),
                          _dv({"@id": E, "@type": "PartDefinition", "declaredName": "E-branch"})],
                       "previousCommit": {"@id": c1}})
    assert status == 200
    _, F_main = _req("GET", f"/projects/{pid}/commits/{mc['@id']}/elements/{F}")
    assert F_main["declaredName"] == "F"
    status, _ = _req("GET", f"/projects/{pid}/commits/{c1}/elements/{F}")
    assert status == 404                                     # lineages isolated


@pytest.mark.integration
def test_verbatim_readback_echo_recommit(proj):
    pid, E, c1 = proj["pid"], proj["E"], proj["c1"]
    _, full = _req("GET", f"/projects/{pid}/commits/{c1}/elements/{E}")
    assert "elementId" in full                               # verbose readback
    status, c2 = _req("POST", f"/projects/{pid}/commits", {"@type": "Commit", "change": [
        _dv(full)], "previousCommit": {"@id": c1}})
    assert status == 200                                     # ground truth 15
    _, back = _req("GET", f"/projects/{pid}/commits/{c2['@id']}/elements/{E}")
    assert back["declaredName"] == "E0"
