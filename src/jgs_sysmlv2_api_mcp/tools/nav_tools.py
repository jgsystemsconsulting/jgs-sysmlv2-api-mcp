# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
def traverse(root, get_children, max_depth=25):
    """Returns {visited: [...], cycle_detected: bool, cycle_nodes: [...]} (SC10).
    Terminates on cycles (visited-set) AND reports them; raises on depth-exceeded."""
    visited, order = set(), []
    cycle_nodes = set()
    stack = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        # Precedence is intentional: an already-visited node is a CYCLE (dedupe +
        # record), checked BEFORE the depth cap. So a tight cycle reports
        # cycle_detected rather than raising depth-exceeded; the depth cap guards
        # genuinely deep ACYCLIC chains, not cycles (which the visited-set bounds).
        if node in visited:
            cycle_nodes.add(node)          # re-encountered -> part of a cycle
            continue
        if depth > max_depth:
            raise ValueError(f"depth-exceeded at {node} (cap {max_depth})")
        visited.add(node)
        order.append(node)
        for child in get_children(node):
            stack.append((child, depth + 1))   # push all; dedupe on pop so cycles are seen
    return {"visited": order, "cycle_detected": bool(cycle_nodes),
            "cycle_nodes": sorted(cycle_nodes)}


def child_ids(api_client, commit_id, element_id):
    """Owned-member ids of an element. Fast route: the server derived
    ownedMember (conformant implementations). Fallback: scan the commit's
    OwningMembership elements (owningRelatedElement -> ownedMemberElement) —
    required on the pilot, which never derives fields (spike ground truth #6).
    ponytail: fallback is an O(n) full-element scan per call; index it in one
    fetch if models outgrow pilot scale."""
    element = api_client.get_element(commit_id, element_id)
    ids = [m["@id"] for m in element.get("ownedMember") or [] if m.get("@id")]
    if ids:
        return ids
    return [
        (el.get("ownedMemberElement") or {}).get("@id")
        for el in api_client.get_elements(commit_id)
        if (el.get("owningRelatedElement") or {}).get("@id") == element_id
        and (el.get("ownedMemberElement") or {}).get("@id")
    ]


def get_children(api_client, commit_id, element_id):
    """One level of containment with the fields an agent actually needs.
    ponytail: one get_element per child (N+1 round trips); batch if a
    multi-id fetch appears on the pilot."""
    out = []
    for cid in child_ids(api_client, commit_id, element_id):
        child = api_client.get_element(commit_id, cid)
        out.append({"id": cid,
                    "name": child.get("declaredName") or child.get("name"),
                    "type": child.get("@type")})
    return out


def filter_root_ids(api_client, commit_id, candidates):
    """The pilot's /roots does not filter server-side (ground truth 2,
    re-verified during T1 implementation) — it returns every element in the
    commit. Excludes any candidate that is an ownedMemberElement of an
    OwningMembership, scanning the same OwningMembership shape child_ids'
    fallback route scans (not shared code — see child_ids).
    ponytail: one full-element scan regardless of candidate count; fine at
    pilot scale."""
    owned = {
        (el.get("ownedMemberElement") or {}).get("@id")
        for el in api_client.get_elements(commit_id)
        if (el.get("ownedMemberElement") or {}).get("@id")
    }
    return [c["@id"] for c in candidates if c["@id"] not in owned]


def find_by_name(api_client, commit_id, name, type=None):
    """Resolve elements by declaredName (agents don't know UUIDs). Sends a
    server-side where clause AND re-filters client-side, so the result is
    correct whether or not the server honours the constraint.
    Ground truth 9 (re-verified): PrimitiveConstraint.value must be an ARRAY
    (matches the pilot's OpenAPI example) — a bare string 500s; "inverse" is
    not part of the pilot's accepted shape and must be omitted.
    ponytail: the pilot doesn't measurably narrow results server-side today
    (client-side filter does all the real work either way) — the where
    clause is kept because it's proven safe and pays off on a server that
    does filter, without changing correctness on one that doesn't."""
    body = {"@type": "Query", "select": [],
            "where": {"@type": "PrimitiveConstraint",
                      "operator": "=", "property": "declaredName", "value": [name]}}
    out = []
    for el in api_client.query(commit_id, body):
        if (el.get("declaredName") or el.get("name")) != name:
            continue
        if type and el.get("@type") != type:
            continue
        out.append({"id": el.get("@id"),
                    "name": el.get("declaredName") or el.get("name"),
                    "type": el.get("@type")})
    return out


def related_ids(api_client, commit_id, element_id):
    """Outgoing relationship targets of an element (element is source) —
    the follow_relationships edge set for nav_traverse. Only relationships
    with explicit source/target are visible (tool-catalog GT 3)."""
    out = []
    for rel in api_client.get_relationships(commit_id, element_id, direction="out"):
        for t in rel.get("target") or []:
            tid = t.get("@id")
            if tid:
                out.append(tid)
    return out
