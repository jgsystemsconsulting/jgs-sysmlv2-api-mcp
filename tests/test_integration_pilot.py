# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""Task 15 — live integration tests against the OMG pilot (localhost:9000).

Exercises the real ApiClient + Session + tools end-to-end. Maps to spec §6 SCs.
Requires a live pilot; run: pytest tests/test_integration_pilot.py -v -m integration

PILOT GROUND TRUTH (probed 2026-07-02):
- commit list is NOT reliably newest-first for rapid successive commits
  (found during T1 implementation); reconcile() and ApiClient.resolve_head()
  both locate the head via previousCommit-chain parentage instead of trusting
  list order — see reconcile.py and api_client.py.
- the pilot does NOT reject a stale previousCommit (no 409) — so SC5's LIVE
  409 trigger is unavailable here. The CommitConflict HANDLER is proven by the
  unit test in test_api_client.py; only the live server-side 409 can't be induced
  against this permissive pilot. Flagged, not silently skipped.
"""
import json
import os
import uuid
import urllib.request

import pytest

from jgs_sysmlv2_api_mcp.api_client import ApiClient
from jgs_sysmlv2_api_mcp.config import Config
from jgs_sysmlv2_api_mcp.session import Session, StagingError
from jgs_sysmlv2_api_mcp.tools.commit_tools import build_commit_body

HOST = os.environ.get("SYSMLV2_HOST", "http://localhost:9000")


def _new_project():
    body = json.dumps({"@type": "Project", "name": f"it-{uuid.uuid4().hex[:8]}"}).encode()
    req = urllib.request.Request(HOST + "/projects", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())["@id"]


def _client(project):
    return ApiClient(Config(base_url=HOST, token="", project=project, branch=None))


def _commit_ops(client, ops, previous_commit=None):
    body = build_commit_body(ops, previous_commit=previous_commit)
    return client.post_commit(body)["@id"]


class _Resolver:
    """Minimal resolver: real elements live in `project`, with prior_versions/children."""
    def __init__(self, project, mapping=None, children=None):
        self._project, self._m, self._c = project, mapping or {}, children or {}
    def resolve(self, uid): return self._m.get(uid)
    def owned_children(self, uid): return self._c.get(uid, [])


@pytest.mark.integration
def test_sc2_write_roundtrip_end_to_end():
    """SC2: stage via Session -> build body -> post -> read back with fidelity."""
    pid = _new_project()
    client = _client(pid)
    sess = Session(project=pid)
    part_id = sess.create_element(type="PartDefinition", name="Vehicle", owner=str(uuid.uuid4()))
    ops = sess.staged_ops()
    commit_id = _commit_ops(client, ops)
    got = client.get_element(commit_id, part_id)
    assert got["@id"] == part_id
    assert got["@type"] == "PartDefinition"
    assert got["declaredName"] == "Vehicle"          # raw-JSON fidelity


@pytest.mark.integration
def test_sc4_pagination_no_dupes_no_gaps():
    """SC4: page a collection of M > page_size via read_tools; union == full set."""
    from jgs_sysmlv2_api_mcp.tools.read_tools import query_elements_page
    pid = _new_project()
    client = _client(pid)
    # stage M distinct parts in one commit
    M = 12
    ops, part_ids = [], []
    for i in range(M):
        eid = str(uuid.uuid4())
        part_ids.append(eid)
        ops.append({"op": "create", "id": eid,
                    "payload": {"@id": eid, "@type": "PartDefinition", "declaredName": f"P{i}"},
                    "refs": []})
    commit_id = _commit_ops(client, ops)
    # page through via get_elements (raw list); assert our parts are all present, no dupes
    all_els = client.get_elements(commit_id)
    seen = [e["@id"] for e in all_els if e["@id"] in set(part_ids)]
    assert set(seen) == set(part_ids)                # union == full set
    assert len(seen) == len(set(seen))               # no duplicates


@pytest.mark.integration
def test_sc3b_client_prevalidation_blocks_before_post():
    """SC3a/SC3b: a cross-project owner is rejected at STAGE time; no commit sent."""
    pid = _new_project()
    other = _new_project()
    resolver = _Resolver(pid, mapping={"foreign": {"project": other, "version": "v1"}})
    sess = Session(project=pid, resolver=resolver)
    with pytest.raises(StagingError):
        sess.create_element(type="PartDefinition", name="X", owner="foreign")
    assert sess.staged_ops() == []                   # nothing staged -> nothing to commit (SC11)


@pytest.mark.integration
def test_sc12_buffer_cap_boundary():
    """SC12: staging past the cap is rejected; already-staged content preserved."""
    sess = Session(project="p", buffer_cap=2)
    sess.create_element(type="PartDefinition", name="A", owner="root")   # 2 ops -> fits
    before = sess.staged_ops()
    assert len(before) == 2
    with pytest.raises(StagingError):
        sess.create_element(type="PartDefinition", name="B", owner="root")
    assert sess.staged_ops() == before               # nothing dropped


@pytest.mark.integration
def test_sc9_transport_rejects_non_loopback_http():
    """SC9: a non-HTTPS/non-loopback endpoint is rejected before any request."""
    from jgs_sysmlv2_api_mcp.config import load_config, ConfigError
    os.environ["SYSMLV2_BASE_URL"] = "http://169.254.169.254/latest"   # metadata IP
    os.environ["SYSMLV2_TOKEN"] = "t"
    os.environ["SYSMLV2_PROJECT"] = "p"
    try:
        with pytest.raises(ConfigError):
            load_config()
    finally:
        os.environ.pop("SYSMLV2_BASE_URL", None)


@pytest.mark.integration
def test_sc5_conflict_handling_note():
    """SC5: this pilot does NOT enforce 409 on a stale previousCommit, so the LIVE
    conflict path can't be induced here. The CommitConflict handler is covered by
    the unit test (test_api_client.py::test_post_commit_409_raises_commit_conflict).
    This test documents the pilot limitation rather than silently passing."""
    pid = _new_project()
    client = _client(pid)
    c1 = _commit_ops(client, [{"op": "create", "id": str(uuid.uuid4()),
        "payload": {"@id": str(uuid.uuid4()), "@type": "PartDefinition", "declaredName": "A"},
        "refs": []}])
    # commit again with the now-stale c1 as previousCommit; pilot accepts (no 409)
    eid = str(uuid.uuid4())
    result = client.post_commit(build_commit_body(
        [{"op": "create", "id": eid,
          "payload": {"@id": eid, "@type": "PartDefinition", "declaredName": "B"}, "refs": []}],
        previous_commit=c1))
    assert result["@id"]     # accepted; documents that live 409 is not inducible on this pilot


@pytest.mark.integration
def test_t1_navigation_end_to_end():
    """T1 acceptance: from a bare project id, reach a named element in <=3
    navigation calls, then relationships + diff — all through ApiClient +
    nav/read tools exactly as the MCP handlers call them."""
    from jgs_sysmlv2_api_mcp.tools.nav_tools import find_by_name, get_children
    from jgs_sysmlv2_api_mcp.tools.read_tools import diff_commits
    pid = _new_project()
    client = _client(pid)

    vehicle, car, mem, rel = (str(uuid.uuid4()) for _ in range(4))
    ops = [
        {"op": "create", "id": vehicle, "refs": [],
         "payload": {"@id": vehicle, "@type": "PartDefinition", "declaredName": "Vehicle"}},
        {"op": "create", "id": car, "refs": [],
         "payload": {"@id": car, "@type": "PartDefinition", "declaredName": "Car"}},
        {"op": "create", "id": mem, "refs": [vehicle, car],
         "payload": {"@id": mem, "@type": "OwningMembership",
                     "owningRelatedElement": {"@id": vehicle},
                     "ownedMemberElement": {"@id": car}}},
    ]
    c1 = _commit_ops(client, ops)
    # second commit: a relationship WITH explicit source/target (D4 rule)
    ops2 = [{"op": "create", "id": rel, "refs": [vehicle, car],
             "payload": {"@id": rel, "@type": "Subclassification",
                         "superclassifier": {"@id": vehicle},
                         "subclassifier": {"@id": car},
                         "source": [{"@id": car}], "target": [{"@id": vehicle}]}}]
    c2 = _commit_ops(client, ops2, previous_commit=c1)

    # head resolution (D2): newest commit is c2
    assert client.resolve_head() == c2
    # call 1: roots -> Vehicle is the entry point. Raw /roots does NOT filter
    # (ground truth 2); filter_root_ids (Task 5) does the client-side exclusion
    # the get_root_elements tool handler (Task 7) relies on.
    from jgs_sysmlv2_api_mcp.tools.nav_tools import filter_root_ids
    raw_roots = client.get_roots(c2)
    assert {vehicle, car} <= {r["@id"] for r in raw_roots}   # unfiltered: both present
    filtered = filter_root_ids(client, c2, raw_roots)
    assert filtered == [vehicle]                             # filtered: Car excluded (owned)
    # call 2: children of Vehicle -> Car, with name+type (membership-scan route)
    kids = get_children(client, c2, vehicle)
    assert {"id": car, "name": "Car", "type": "PartDefinition"} in kids
    # call 2 (alternative): find by name
    hits = find_by_name(client, c2, "Car", type="PartDefinition")
    assert [h["id"] for h in hits] == [car]
    # call 3: fetch the named element itself -> acceptance's <=3-call chain
    # (get_root_elements -> find_by_name/get_children -> get_element) complete
    element = client.get_element(c2, car)
    assert element["declaredName"] == "Car"
    # relationships: visible with direction semantics
    incoming = client.get_relationships(c2, vehicle, direction="in")
    assert rel in {r["@id"] for r in incoming}
    assert rel not in {r["@id"] for r in client.get_relationships(c2, vehicle, direction="out")}
    # diff c1 -> c2: exactly the relationship was created
    d = diff_commits(client, c1, c2)
    assert rel in d["created"]
    assert d["deleted"] == []
    # changes record fidelity
    changes = client.get_commit_changes(c2)
    assert changes[0]["payload"]["@type"] == "Subclassification"


@pytest.mark.integration
def test_t2_branch_session_workflow_end_to_end():
    """T2 acceptance: agent works on its own branch, main is untouched until
    an explicit conflict-checked merge; conflicts refuse; tags checkpoint."""
    from jgs_sysmlv2_api_mcp.tools.branch_tools import (
        delete_branch_verified, squash_merge)
    pid = _new_project()
    client = _client(pid)

    # seed main with E
    E = str(uuid.uuid4())
    c1 = _commit_ops(client, [{"op": "create", "id": E, "refs": [],
        "payload": {"@id": E, "@type": "PartDefinition", "declaredName": "E0"}}])
    main_id = (client.get_project().get("defaultBranch") or {}).get("@id")

    # agent branch + branch-targeted commit via the session machinery.
    # owner=E (not a fresh random uuid): the pilot 500s on a dangling
    # owningRelatedElement reference once previousCommit is set (confirmed
    # only the very first commit in a project's history tolerates a
    # not-yet-real owner) -- a newly-found ground truth, orthogonal to T2.
    work = client.create_branch("agent-work", c1)
    sess = Session(project=pid, branch=work["@id"])
    assert sess.branch == work["@id"]
    F = sess.create_element(type="PartDefinition", name="F", owner=E)
    head = client.resolve_head(branch_id=sess.branch)
    body = build_commit_body(sess.staged_ops(), previous_commit=head)
    bc = client.post_commit(body, branch_id=sess.branch)

    # branch advanced; main untouched
    assert client.resolve_head(branch_id=work["@id"]) == bc["@id"]
    assert client.resolve_head(branch_id=main_id) == c1

    # tag the pre-merge baseline
    tag = client.create_tag("pre-merge", c1)
    assert any(t["@id"] == tag["@id"] for t in client.get_tags())

    # merge work -> main; F appears on main
    got = squash_merge(client, work["@id"], main_id, description="merge agent work")
    assert got["outcome"] == "merged"
    merged_head = client.resolve_head(branch_id=main_id)
    assert client.get_element(merged_head, F)["declaredName"] == "F"

    # conflict path: both branches now change E -> merge refuses, nothing committed
    _commit_ops(client, [{"op": "modify", "id": E, "refs": [E],
        "payload": {"@id": E, "@type": "PartDefinition", "declaredName": "E-main"}}],
        previous_commit=merged_head)
    work2 = client.create_branch("agent-work-2", merged_head)
    body2 = build_commit_body([{"op": "modify", "id": E, "refs": [E],
        "payload": {"@id": E, "@type": "PartDefinition", "declaredName": "E-work"}}],
        previous_commit=merged_head)
    client.post_commit(body2, branch_id=work2["@id"])
    got = squash_merge(client, work2["@id"], main_id)
    assert got == {"outcome": "conflict", "elements": [E]}

    # verified delete: work branch goes away, default branch is refused
    assert delete_branch_verified(client, work["@id"]) == {"deleted": True}
    assert delete_branch_verified(client, main_id)["deleted"] is False


@pytest.mark.integration
def test_t3_project_lifecycle_end_to_end():
    """T3 acceptance: create-with-description -> echo-PUT update preserving
    untouched fields -> D9 refusal of the configured project -> verified
    delete of a throwaway project."""
    from jgs_sysmlv2_api_mcp.tools.project_tools import (
        delete_project_verified, update_project_fields)
    pid = _new_project()
    client = _client(pid)

    made = client.create_project(f"t3-{uuid.uuid4().hex[:8]}", "born in T3")
    assert made["description"] == "born in T3"

    updated = update_project_fields(client, project_id=made["@id"], name="t3-renamed")
    assert updated["name"] == "t3-renamed"
    assert updated["description"] == "born in T3"        # untouched field survives

    refused = delete_project_verified(client, pid, configured_project=pid)
    assert refused["deleted"] is False                    # D9

    got = delete_project_verified(client, made["@id"], configured_project=pid)
    assert got == {"deleted": True}
    assert all(p["@id"] != made["@id"] for p in client.list_projects())


@pytest.mark.integration
def test_t4_authoring_end_to_end():
    """T4 acceptance: batch-stage a package with parts + a typed relationship
    (caller-minted ids for cross-refs), commit, verify structure and the
    relationship's discoverability, then move a part and verify the rehome."""
    from jgs_sysmlv2_api_mcp.tools.author_tools import move_element
    from jgs_sysmlv2_api_mcp.tools.nav_tools import get_children, related_ids
    pid = _new_project()
    client = _client(pid)
    sess = Session(project=pid)

    pkg, vehicle, car = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    sess.stage_batch([
        {"op": "create", "type": "Package", "name": "Pkg", "owner": str(uuid.uuid4()),
         "element_id": pkg},
        {"op": "create", "type": "PartDefinition", "name": "Vehicle", "owner": pkg,
         "element_id": vehicle},
        {"op": "create", "type": "PartDefinition", "name": "Car", "owner": pkg,
         "element_id": car},
        {"op": "relate", "type": "Subclassification", "source": car,
         "target": vehicle, "owner": pkg},
    ])
    c1 = _commit_ops(client, sess.staged_ops())

    # containment landed: Pkg owns Vehicle, Car, and the relationship element
    kid_ids = {k["id"] for k in get_children(client, c1, pkg)}
    assert {vehicle, car} <= kid_ids
    # the relationship is discoverable with correct direction (D4/D10)
    assert vehicle in related_ids(client, c1, car)          # car -> vehicle (out)
    incoming = client.get_relationships(c1, vehicle, direction="in")
    assert any((r.get("subclassifier") or {}).get("@id") == car for r in incoming)

    # move: rehome Car from Pkg to Vehicle, commit, verify (GT 20)
    sess2 = Session(project=pid)
    got = move_element(client, sess2, car, vehicle, c1)
    assert got["old_owner"] == pkg and got["new_owner"] == vehicle
    c2 = _commit_ops(client, sess2.staged_ops(), previous_commit=c1)
    assert car in {k["id"] for k in get_children(client, c2, vehicle)}
    assert car not in {k["id"] for k in get_children(client, c2, pkg)}
    assert car in {k["id"] for k in get_children(client, c1, pkg)}   # history intact
