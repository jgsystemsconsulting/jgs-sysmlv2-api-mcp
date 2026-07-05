# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""T1 spike tests — pin the pilot HTTP contract (RESULT: PASS 2026-07-02).

Ground truths encoded (see docs/dev/tool-catalog.md "Pilot spike results"):
roots shape, /relationships matches only explicit source/target,
direction=in|out|both semantics, /changes full DataVersion fidelity,
branch-targeted commits isolate branches, containment is NOT derived
(ownedMember empty; discovery scans OwningMembership elements), and the
pilot 404s the native diff + merge endpoints it advertises in its OpenAPI.

Uses urllib (not our ApiClient) so the contract is pinned independent of
our wrapper. Requires a live pilot:
  SYSMLV2_HOST=http://localhost:9000 pytest tests/test_spike_t1_endpoints.py -v -m integration
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


@pytest.fixture()
def model():
    """Project with: Vehicle, Car (parts), Car-owned-by-Vehicle membership,
    Subclassification Car->Vehicle WITH explicit source/target."""
    _, proj = _req("POST", "/projects",
                   {"@type": "Project", "name": f"t1spike-{uuid.uuid4().hex[:8]}"})
    pid = proj["@id"]
    vehicle, car, mem, rel = (str(uuid.uuid4()) for _ in range(4))
    status, c1 = _req("POST", f"/projects/{pid}/commits", {"@type": "Commit", "change": [
        _dv({"@id": vehicle, "@type": "PartDefinition", "declaredName": "Vehicle"}),
        _dv({"@id": car, "@type": "PartDefinition", "declaredName": "Car"}),
        _dv({"@id": mem, "@type": "OwningMembership",
             "owningRelatedElement": {"@id": vehicle},
             "ownedMemberElement": {"@id": car}}),
        _dv({"@id": rel, "@type": "Subclassification",
             "superclassifier": {"@id": vehicle}, "subclassifier": {"@id": car},
             "source": [{"@id": car}], "target": [{"@id": vehicle}]}),
    ]})
    assert status == 200, f"model commit failed: {status}"
    return {"pid": pid, "commit": c1["@id"],
            "vehicle": vehicle, "car": car, "mem": mem, "rel": rel}


@pytest.mark.integration
def test_project_carries_default_branch(model):
    status, proj = _req("GET", f"/projects/{model['pid']}")
    assert status == 200
    assert proj["defaultBranch"]["@id"]                     # ground truth 1


@pytest.mark.integration
def test_roots_does_not_filter_owned_elements(model):
    """Ground truth 2 (re-verified): /roots returns full-fidelity elements
    but does NOT exclude owned ones — Vehicle (unowned) AND Car (owned by
    Vehicle via an explicit OwningMembership) both appear. get_root_elements
    (Task 3/7) must filter client-side using the same containment-scan
    child_ids relies on (ground truth 6)."""
    status, roots = _req("GET", f"/projects/{model['pid']}/commits/{model['commit']}/roots")
    assert status == 200
    ids = {r["@id"] for r in roots}
    assert model["vehicle"] in ids
    assert model["car"] in ids                              # NOT excluded — server doesn't filter


@pytest.mark.integration
def test_relationships_match_only_explicit_source_target(model):
    base = f"/projects/{model['pid']}/commits/{model['commit']}/elements"
    # rel HAS source/target -> visible, with direction semantics
    _, both = _req("GET", f"{base}/{model['vehicle']}/relationships?direction=both")
    assert model["rel"] in {r["@id"] for r in both}
    _, incoming = _req("GET", f"{base}/{model['vehicle']}/relationships?direction=in")
    assert model["rel"] in {r["@id"] for r in incoming}     # vehicle is target
    _, outgoing = _req("GET", f"{base}/{model['vehicle']}/relationships?direction=out")
    assert model["rel"] not in {r["@id"] for r in outgoing}
    # the OwningMembership (NO source/target arrays) is INVISIBLE here
    _, mem_side = _req("GET", f"{base}/{model['vehicle']}/relationships?direction=both")
    assert model["mem"] not in {r["@id"] for r in mem_side}  # ground truth 3


@pytest.mark.integration
def test_containment_not_derived_membership_scan_required(model):
    base = f"/projects/{model['pid']}/commits/{model['commit']}"
    # ground truth 6a: the pilot does NOT derive ownedMember
    _, vehicle = _req("GET", f"{base}/elements/{model['vehicle']}")
    assert not vehicle.get("ownedMember")
    # ground truth 6b: the membership scan DOES find the child
    _, elements = _req("GET", f"{base}/elements")
    children = [(e.get("ownedMemberElement") or {}).get("@id") for e in elements
                if (e.get("owningRelatedElement") or {}).get("@id") == model["vehicle"]]
    assert children == [model["car"]]


@pytest.mark.integration
def test_changes_full_dataversion_fidelity(model):
    status, changes = _req("GET",
        f"/projects/{model['pid']}/commits/{model['commit']}/changes")
    assert status == 200 and len(changes) == 4
    by_id = {c["identity"]["@id"]: c for c in changes}
    assert by_id[model["vehicle"]]["payload"]["declaredName"] == "Vehicle"
    assert "changeType" not in changes[0]                   # ground truth 4: no discriminator


@pytest.mark.integration
def test_branch_targeted_commit_isolates_branches(model):
    pid = model["pid"]
    status, branch = _req("POST", f"/projects/{pid}/branches",
        {"@type": "Branch", "name": "t1spike", "head": {"@id": model["commit"]}})
    assert status == 200
    _, before = _req("GET", f"/projects/{pid}")
    main_id = before["defaultBranch"]["@id"]
    extra = str(uuid.uuid4())
    status, bc = _req("POST", f"/projects/{pid}/commits?branchId={branch['@id']}",
        {"@type": "Commit", "change": [
            _dv({"@id": extra, "@type": "PartDefinition", "declaredName": "Boat"})]})
    assert status == 200
    assert bc["previousCommit"]["@id"] == model["commit"]   # ground truth 5 (branch head)
    _, branches = _req("GET", f"/projects/{pid}/branches")
    heads = {b["@id"]: b["head"]["@id"] for b in branches}
    assert heads[branch["@id"]] == bc["@id"]                # branch advanced
    assert heads[main_id] == model["commit"]                # main untouched


@pytest.mark.integration
def test_query_results_where_clause_is_a_safe_filter(model):
    """find_by_name (Task 6) sends a PrimitiveConstraint where-clause and also
    re-filters client-side. This pins that the pilot's /query-results either
    honours the where-clause or safely over-returns (never errors, never
    silently returns a wrong/empty result the client-side filter can't
    correct) — i.e. find_by_name's belt-and-braces re-filter is sufficient.

    Ground truth 9 (path correction): /query-results is PROJECT-scoped with
    commitId as a query param, not /commits/{c}/query-results (that 404s).
    QueryRequest also requires a "name" field. PrimitiveConstraint.value must
    be an ARRAY (matches the OpenAPI example) — a bare string 500s; "inverse"
    is not part of the pilot's accepted shape and must be omitted."""
    base = f"/projects/{model['pid']}/query-results?commitId={model['commit']}"
    body = {"@type": "Query", "name": "spike-test-find-vehicle", "select": [],
            "where": {"@type": "PrimitiveConstraint",
                      "operator": "=", "property": "declaredName", "value": ["Vehicle"]}}
    status, results = _req("POST", base, body)
    assert status == 200                                    # ground truth 9: no error on this shape
    ids = {r["@id"] for r in results}
    assert model["vehicle"] in ids                           # matching element present either way


@pytest.mark.integration
def test_native_diff_and_merge_unimplemented_on_pilot(model):
    """Pinned so a pilot upgrade that implements them gets noticed."""
    pid, cid = model["pid"], model["commit"]
    status, _ = _req("GET", f"/projects/{pid}/commits/{cid}/diff?baseCommitId={cid}")
    assert status == 404                                    # ground truth 7
    _, proj = _req("GET", f"/projects/{pid}")
    status, _ = _req("POST",
        f"/projects/{pid}/branches/{proj['defaultBranch']['@id']}/merge?sourceCommitId={cid}")
    assert status == 404                                    # ground truth 8
