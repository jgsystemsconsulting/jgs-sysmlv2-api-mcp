# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
import secrets
import threading

from .ids import fingerprint, new_uuid


class StagingError(Exception):
    pass


class TokenError(Exception):
    pass


# D10 — concrete end fields per relationship type: (source_field, target_field,
# ends_are_arrays). source = the specific/dependent end, target = the general
# end (matches /relationships direction semantics, tool-catalog GT 3). Types
# not listed get source/target only; callers supply concrete ends via
# `properties`.
RELATIONSHIP_END_FIELDS = {
    "Subclassification": ("subclassifier", "superclassifier", False),
    "Specialization": ("specific", "general", False),
    "Subsetting": ("subsettingFeature", "subsettedFeature", False),
    "Redefinition": ("redefiningFeature", "redefinedFeature", False),
    "FeatureTyping": ("typedFeature", "type", False),
    "Dependency": ("client", "supplier", True),
}


class Session:
    # FINAL v0 signature + T2 extension: `branch` (D8 active-branch id) was
    # added in T2; everything else is unchanged from v0.
    def __init__(self, project: str, buffer_cap: int = 5000,
                 clock=None, token_ttl: float = 120.0, resolver=None,
                 branch: str | None = None):
        import time as _time
        self._project = project
        self._cap = buffer_cap
        self._ops: list[dict] = []          # ordered op list
        self._lock = threading.RLock()      # RLock: create/delete call helpers that also lock
        self._clock = clock or _time.monotonic   # injectable for TTL tests (Task 7)
        self._token_ttl = token_ttl               # confirm-token TTL seconds (Task 7)
        self._token = None                        # {value, fp, issued, consumed} (Task 7)
        self._resolver = resolver                 # real-element/project resolver (Task 8)
        self._in_flight = False                   # commit-in-flight guard (Task 7)
        self._branch = branch                    # active branch id (T2, D8)

    def _op_count(self) -> int:
        return len(self._ops)

    def _check_cap(self, adding: int):
        if self._op_count() + adding > self._cap:
            raise StagingError("staging buffer full — commit or discard pending changes before adding more")

    def _check_scope(self, ref_uuid: str):
        # SC11/SC3a: a reference to an element in ANOTHER project may not be staged.
        # Buffer-local ids (not yet committed) have no resolver entry and are allowed.
        if self._resolver is None:
            return
        info = self._resolver.resolve(ref_uuid)
        if info is not None and info["project"] != self._project:
            raise StagingError(
                f"cross-project reference rejected: {ref_uuid} in {info['project']}")

    def create_element(self, type: str, name: str, owner: str,
                       element_id: str | None = None) -> str:
        with self._lock:
            # reject a cross-project owner BEFORE staging (SC3a: commit never leaves).
            staged_ids = {o["id"] for o in self._ops}
            if owner not in staged_ids:
                self._check_scope(owner)
            eid, mid = element_id or new_uuid(), new_uuid()
            element_op = {"op": "create", "id": eid,
                          "payload": {"@id": eid, "@type": type, "declaredName": name},
                          "refs": [owner]}
            membership_op = {"op": "create", "id": mid,
                             "payload": {"@id": mid, "@type": "OwningMembership",
                                         "owningRelatedElement": {"@id": owner},
                                         "ownedMemberElement": {"@id": eid}},
                             "refs": [owner, eid]}
            self._check_cap(2)
            self._ops.append(element_op)
            self._ops.append(membership_op)
            return eid

    def create_relationship(self, type: str, source: str, target: str,
                            owner: str | None = None,
                            properties: dict | None = None) -> str:
        """Stage a typed relationship element. Always sets explicit source/
        target arrays (D4 — the pilot never derives them and /relationships
        matches on nothing else) plus the type's concrete end fields from
        RELATIONSHIP_END_FIELDS (D10). Optional owner synthesizes an
        OwningMembership, mirroring create_element."""
        with self._lock:
            staged_ids = {o["id"] for o in self._ops}
            for ref in (source, target, owner):
                if ref is not None and ref not in staged_ids:
                    self._check_scope(ref)
            rid = new_uuid()
            payload = {"@id": rid, "@type": type,
                       "source": [{"@id": source}], "target": [{"@id": target}]}
            ends = RELATIONSHIP_END_FIELDS.get(type)
            if ends:
                source_field, target_field, as_array = ends
                payload[source_field] = [{"@id": source}] if as_array else {"@id": source}
                payload[target_field] = [{"@id": target}] if as_array else {"@id": target}
            if properties:
                payload.update(properties)
            ops = [{"op": "create", "id": rid, "payload": payload,
                    "refs": [r for r in (source, target, owner) if r]}]
            if owner:
                mid = new_uuid()
                ops.append({"op": "create", "id": mid,
                            "payload": {"@id": mid, "@type": "OwningMembership",
                                        "owningRelatedElement": {"@id": owner},
                                        "ownedMemberElement": {"@id": rid}},
                            "refs": [owner, rid]})
            self._check_cap(len(ops))
            self._ops.extend(ops)
            return rid

    def delete_element(self, element_id: str):
        with self._lock:
            staged = [o for o in self._ops if o["id"] == element_id]
            has_create = any(o["op"] == "create" for o in staged)
            has_modify = any(o["op"] == "modify" for o in staged)
            if has_create:
                # create-then-delete in-batch -> drop element + its synthesized membership
                self._ops = [o for o in self._ops
                             if o["id"] != element_id
                             and o.get("payload", {}).get("ownedMemberElement", {}).get("@id") != element_id]
                return
            if has_modify:
                # modify-then-delete of a real element -> collapse to one delete
                # (the earlier modify is discarded; delete subsumes it)
                self._ops = [o for o in self._ops if o["id"] != element_id]
            # SC6 bounded delete: refuse to delete an element that OWNS children
            # (no silent cascade). Owned-children lookup uses the resolver; if it
            # reports children, error and tell the caller to use delete_subtree.
            if self._resolver is not None:
                children = self._resolver.owned_children(element_id)
                if children:
                    raise StagingError(
                        f"element {element_id} owns {len(children)} child(ren); "
                        f"delete them explicitly or use delete_subtree")
            # real element delete: stage a delete DataVersion (payload=None) carrying
            # the prior_version so the API versions the delete against the existing
            # element (same real-element requirement as modify; spec §4).
            info = self._resolver.resolve(element_id) if self._resolver else None
            self._ops.append({"op": "delete", "id": element_id, "payload": None,
                              "identity": {"@id": element_id},
                              "prior_version": info["version"] if info else None,
                              "refs": [element_id]})

    def modify_element(self, element_id: str, changes: dict):
        with self._lock:
            self._check_scope(element_id)
            # merge: modify-then-modify collapses; modify after in-batch create merges into create
            for o in self._ops:
                if o["id"] == element_id and o["op"] == "create":
                    o["payload"].update(changes)
                    return
                if o["id"] == element_id and o["op"] == "modify":
                    o["payload"].update(changes)
                    return
            info = self._resolver.resolve(element_id) if self._resolver else {"version": None}
            self._check_cap(1)
            self._ops.append({"op": "modify", "id": element_id,
                              "payload": {"@id": element_id, **changes},
                              "identity": {"@id": element_id},
                              "prior_version": info["version"] if info else None,
                              "refs": [element_id]})

    def delete_subtree(self, element_id: str) -> list[str]:
        """Resolve the owned subtree (element_id + all descendants via the
        resolver's owned_children), cap-check the WHOLE set atomically (reject
        wholesale on breach, leaving the buffer unmutated), then stage a
        delete for every id. A subtree delete subsumes any prior staged op
        for a descendant (that earlier create/modify is dropped in favor of
        the delete). Returns the id list as the dry-run diff."""
        with self._lock:
            self._check_scope(element_id)
            subtree_ids: list[str] = []
            seen: set[str] = set()
            stack = [element_id]
            while stack:
                node = stack.pop()
                if node in seen:
                    continue
                seen.add(node)
                subtree_ids.append(node)
                children = self._resolver.owned_children(node) if self._resolver else []
                stack.extend(children)

            # atomic cap-check over the WHOLE subtree before mutating anything:
            # count net-new ops (ids not already staged as a delete for that id).
            to_append = [nid for nid in subtree_ids
                         if not any(o["id"] == nid and o["op"] == "delete" for o in self._ops)]
            self._check_cap(len(to_append))

            for nid in subtree_ids:
                info = self._resolver.resolve(nid) if self._resolver else None
                # subsume: drop any earlier staged op for this id (create/modify/delete)
                self._ops = [o for o in self._ops if o["id"] != nid]
                self._ops.append({"op": "delete", "id": nid, "payload": None,
                                  "identity": {"@id": nid},
                                  "prior_version": info["version"] if info else None,
                                  "refs": [nid]})
            return subtree_ids

    def stage_batch(self, operations: list[dict]) -> list[str]:
        """Stage a whole batch atomically (D12): on ANY failure the buffer is
        restored verbatim to its pre-batch state. Returns one staged id per
        op in order. Create ops may carry a caller-minted element_id — that
        is how later ops in the same batch reference earlier ones."""
        with self._lock:                       # RLock: dispatched methods re-lock
            # deep-copy payload dicts, not just the outer list: modify_element
            # mutates an existing staged op's payload in place
            # (o["payload"].update(changes)) when the target id is already
            # staged as a create/modify. A shallow `list(self._ops)` snapshot
            # would share those payload dict references, so a later in-batch
            # failure would roll back the ops list but leave the mutation —
            # breaking D12's byte-identical guarantee. Guard against None:
            # delete ops carry payload=None (real-element delete versions
            # against prior_version, no payload) — dict(None) raises TypeError.
            snapshot = [dict(o, payload=dict(o["payload"]) if o["payload"] is not None else None)
                       for o in self._ops]
            staged: list[str] = []
            try:
                for op in operations:
                    kind = op.get("op")
                    if kind == "create":
                        staged.append(self.create_element(
                            type=op["type"], name=op["name"], owner=op["owner"],
                            element_id=op.get("element_id")))
                    elif kind == "relate":
                        staged.append(self.create_relationship(
                            type=op["type"], source=op["source"], target=op["target"],
                            owner=op.get("owner"), properties=op.get("properties")))
                    elif kind == "modify":
                        self.modify_element(op["element_id"], op["changes"])
                        staged.append(op["element_id"])
                    elif kind == "delete":
                        self.delete_element(op["element_id"])
                        staged.append(op["element_id"])
                    else:
                        raise StagingError(f"unknown batch op: {kind!r}")
            except Exception:
                self._ops = snapshot           # D12: all-or-nothing
                raise
            return staged

    def staged_ops(self) -> list[dict]:
        return list(self._ops)

    def discard(self):
        with self._lock:
            self._ops = []
            self._token = None      # explicit cancellation invalidates any outstanding token

    @property
    def branch(self) -> str | None:
        return self._branch

    def set_branch(self, branch_id: str | None):
        """Retarget the session at a branch (D6): refuse while staged work
        exists — retargeting mid-review must never silently redirect it —
        and invalidate any outstanding confirm token."""
        with self._lock:
            if self._ops:
                raise StagingError(
                    "staged buffer not empty — commit or discard before switching branch")
            self._branch = branch_id
            self._token = None

    def _prior_versions(self) -> dict:
        """Prior-versions of the real elements referenced by staged ops. Derived
        from the buffer itself (modify/delete ops carry prior_version, set at stage
        time from the resolver), so the fingerprint ALWAYS binds real-element prior
        versions — the caller never has to supply them, and can't accidentally pass
        {} and defeat the SC5/SC8 referenced-element-changed invariant."""
        return {o["id"]: o["prior_version"]
                for o in self._ops
                if o.get("prior_version") is not None}

    def review_changes(self) -> dict:
        with self._lock:
            fp = fingerprint(self._ops, self._prior_versions())
            self._token = {"value": secrets.token_urlsafe(32), "fp": fp,
                           "issued": self._clock(), "consumed": False}
            return {"ops": list(self._ops), "confirm_token": self._token["value"]}

    def _invalidate_token(self):
        self._token = None

    def verify_and_consume(self, token: str) -> list[dict]:
        """Verify-under-lock (CAS on fingerprint over the CURRENT buffer, including
        its real-element prior_versions). Returns the frozen snapshot to commit."""
        with self._lock:
            t = self._token
            if t is None or token != t["value"]:
                raise TokenError("missing or unknown confirm token")
            if t["consumed"]:
                raise TokenError("token already consumed")
            if self._clock() - t["issued"] > self._token_ttl:
                self._token = None
                raise TokenError("token expired")
            current_fp = fingerprint(self._ops, self._prior_versions())
            if current_fp != t["fp"]:
                self._token = None
                raise TokenError("buffer fingerprint changed since review; re-review required")
            t["consumed"] = True
            snapshot = [dict(o) for o in self._ops]     # immutable copy for the network call
            return snapshot

    # --- commit-in-flight guard + snapshot-scoped clear (spec §4) ---
    def begin_commit(self, token: str) -> list[dict]:
        """Verify the token and reserve the commit slot atomically. Raises if a
        commit is already in flight (v1 single-session, but the guard makes a
        double-commit a clean error, not a race)."""
        with self._lock:
            if self._in_flight:
                raise TokenError("a commit is already in flight")
            snapshot = self.verify_and_consume(token)   # re-entrant: RLock
            self._in_flight = True
            return snapshot

    def finish_commit(self, snapshot: list[dict]):
        """On success: remove EXACTLY the committed ops from the buffer, so any op
        staged during the (lock-free) network POST survives; release the guard."""
        with self._lock:
            committed_ids = {(o["op"], o["id"]) for o in snapshot}
            self._ops = [o for o in self._ops if (o["op"], o["id"]) not in committed_ids]
            self._in_flight = False

    def abort_commit(self):
        """On ambiguous/failed commit: release the guard only; buffer untouched."""
        with self._lock:
            self._in_flight = False
