# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""T2 — branch lifecycle + client-side squash-merge.

The pilot advertises POST .../branches/{target}/merge in its OpenAPI but
404s it (tool-catalog spike ground truth 8), so merge is client-side:
divergence via previousCommit parentage, element-set diff of both sides,
refuse on overlap (D7), replay the source's net payloads onto the target as
one commit. Verbatim readback replay (GT 15) and prior-less versioning
(GT 13) are pilot-verified, so no DataVersion bookkeeping is needed.
Swap to the native endpoint against a conformant server."""
from .read_tools import diff_commits


def find_divergence(commits, source_head, target_head):
    """Nearest ancestor of source_head that is also an ancestor-or-self of
    target_head, walking previousCommit parentage. None if lineages are
    disjoint (foreign project/branch mix-up — caller treats as error)."""
    parent = {c["@id"]: (c.get("previousCommit") or {}).get("@id") for c in commits}
    ancestors = set()
    node = target_head
    while node:
        ancestors.add(node)
        node = parent.get(node)
    node = source_head
    while node:
        if node in ancestors:
            return node
        node = parent.get(node)
    return None


def delete_branch_verified(api_client, branch_id):
    """Refuse the default branch client-side (clear error instead of the
    pilot's opaque 500), fire the DELETE, then VERIFY via the branch list —
    the pilot returns 500 even on success (GT 11), so status means nothing."""
    default = (api_client.get_project().get("defaultBranch") or {}).get("@id")
    if branch_id == default:
        return {"deleted": False,
                "reason": "refusing to delete the project default branch"}
    api_client.delete_branch(branch_id)
    remaining = {b["@id"] for b in api_client.get_branches()}
    return {"deleted": branch_id not in remaining}


def squash_merge(api_client, source_branch_id, target_branch_id, description=None):
    """Squash-merge source branch onto target as ONE commit. D7 conflict
    rule: any element changed on BOTH lineages since divergence aborts the
    merge with the conflicting ids — no auto-resolution, nothing committed.
    ponytail: two full element-set diffs per merge (reuses diff_commits);
    fine at pilot scale, walk /changes per lineage if models outgrow it."""
    source_head = (api_client.get_branch(source_branch_id).get("head") or {}).get("@id")
    target_head = (api_client.get_branch(target_branch_id).get("head") or {}).get("@id")
    if not source_head or not target_head:
        return {"outcome": "error", "reason": "source or target branch has no head"}
    divergence = find_divergence(api_client.get_commits(), source_head, target_head)
    if divergence is None:
        return {"outcome": "error", "reason": "no common ancestor between branches"}
    if source_head == divergence:
        return {"outcome": "nothing-to-merge"}

    src = diff_commits(api_client, divergence, source_head)
    tgt = diff_commits(api_client, divergence, target_head)
    src_changed = set(src["created"]) | set(src["modified"]) | set(src["deleted"])
    tgt_changed = set(tgt["created"]) | set(tgt["modified"]) | set(tgt["deleted"])
    conflicts = sorted(src_changed & tgt_changed)
    if conflicts:
        return {"outcome": "conflict", "elements": conflicts}

    change = []
    for eid in src["created"] + src["modified"]:
        payload = api_client.get_element(source_head, eid)     # verbatim replay (GT 15)
        change.append({"@type": "DataVersion", "payload": payload,
                       "identity": {"@id": eid, "@type": "DataIdentity"}})
    for eid in src["deleted"]:
        change.append({"@type": "DataVersion", "payload": None,  # prior-less delete (GT 13)
                       "identity": {"@id": eid, "@type": "DataIdentity"}})
    body = {"@type": "Commit", "change": change,
            "previousCommit": {"@id": target_head}}
    if description:
        body["description"] = description
    result = api_client.post_commit(body, branch_id=target_branch_id)
    return {"outcome": "merged", "commit_id": result.get("@id"),
            "created": src["created"], "modified": src["modified"],
            "deleted": src["deleted"]}
