# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""T4 spike tests — pin the pilot HTTP contract (RESULT: PASS 2026-07-03).

Ground truths encoded (docs/dev/tool-catalog.md "Pilot spike results" 20-21):
membership rehome via prior-less modify, and Dependency array-end
round-trip + discoverability. urllib on purpose — pins the HTTP contract
independent of our ApiClient. Requires a live pilot:
  SYSMLV2_HOST=http://localhost:9000 pytest tests/test_spike_t4_endpoints.py -v -m integration
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


def _dv(payload):
    return {"@type": "DataVersion", "payload": payload,
            "identity": {"@id": payload["@id"], "@type": "DataIdentity"}}


def _new_project():
    _, p = _req("POST", "/projects",
                {"@type": "Project", "name": f"t4spike-{uuid.uuid4().hex[:8]}"})
    return p["@id"]


def _membership_children(pid, cid, owner):
    _, els = _req("GET", f"/projects/{pid}/commits/{cid}/elements")
    return [(e.get("ownedMemberElement") or {}).get("@id") for e in els
            if (e.get("owningRelatedElement") or {}).get("@id") == owner]


@pytest.mark.integration
def test_membership_rehome_moves_child_history_intact():
    pid = _new_project()
    A, B, C, M = (str(uuid.uuid4()) for _ in range(4))
    status, c1 = _req("POST", f"/projects/{pid}/commits", {"@type": "Commit", "change": [
        _dv({"@id": A, "@type": "PartDefinition", "declaredName": "OwnerA"}),
        _dv({"@id": B, "@type": "PartDefinition", "declaredName": "OwnerB"}),
        _dv({"@id": C, "@type": "PartDefinition", "declaredName": "Child"}),
        _dv({"@id": M, "@type": "OwningMembership",
             "owningRelatedElement": {"@id": A}, "ownedMemberElement": {"@id": C}})]})
    assert status == 200
    # prior-less modify of the membership rehomes C from A to B (GT 20)
    status, c2 = _req("POST", f"/projects/{pid}/commits", {"@type": "Commit", "change": [
        _dv({"@id": M, "@type": "OwningMembership",
             "owningRelatedElement": {"@id": B}, "ownedMemberElement": {"@id": C}})],
        "previousCommit": {"@id": c1["@id"]}})
    assert status == 200
    assert _membership_children(pid, c2["@id"], A) == []
    assert _membership_children(pid, c2["@id"], B) == [C]
    assert _membership_children(pid, c1["@id"], A) == [C]      # history intact


@pytest.mark.integration
def test_dependency_array_ends_roundtrip_and_discoverable():
    pid = _new_project()
    A, B, D = (str(uuid.uuid4()) for _ in range(3))
    status, c1 = _req("POST", f"/projects/{pid}/commits", {"@type": "Commit", "change": [
        _dv({"@id": A, "@type": "PartDefinition", "declaredName": "ClientPart"}),
        _dv({"@id": B, "@type": "PartDefinition", "declaredName": "SupplierPart"}),
        _dv({"@id": D, "@type": "Dependency",
             "client": [{"@id": A}], "supplier": [{"@id": B}],
             "source": [{"@id": A}], "target": [{"@id": B}]})]})
    assert status == 200
    cid = c1["@id"]
    _, back = _req("GET", f"/projects/{pid}/commits/{cid}/elements/{D}")
    assert back["client"] == [{"@id": A}]                       # GT 21: arrays verbatim
    assert back["supplier"] == [{"@id": B}]
    _, outgoing = _req("GET",
        f"/projects/{pid}/commits/{cid}/elements/{A}/relationships?direction=out")
    assert D in {r["@id"] for r in outgoing}                    # discoverable (GT 3)
