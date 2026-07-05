# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""Task 8 — author tools (spec §4 STAGE-only mutation surface).

These are thin adapters over `Session` (session.py, Tasks 6-8), which owns
all staging/merge/cap/scope logic under its lock. The functions here exist
so `server.py` (Task 14) has a stable, tool-shaped entry point per author
verb, mirroring the read_tools/commit_tools/nav_tools module pattern. No
control flow or validation lives here — it all lives in Session.
"""


def create_element(session, type: str, name: str, owner: str) -> str:
    return session.create_element(type=type, name=name, owner=owner)


def modify_element(session, element_id: str, changes: dict):
    return session.modify_element(element_id, changes)


def delete_element(session, element_id: str):
    return session.delete_element(element_id)


def delete_subtree(session, element_id: str) -> list[str]:
    return session.delete_subtree(element_id)


def create_relationship(session, type: str, source: str, target: str,
                        owner: str | None = None, properties: dict | None = None) -> str:
    return session.create_relationship(type=type, source=source, target=target,
                                       owner=owner, properties=properties)


def move_element(api_client, session, element_id: str, new_owner: str,
                 commit_id: str) -> dict:
    """D11 — rehome an element by staging a prior-less modify of its unique
    OwningMembership at the given commit (verified live: tool-catalog GT 20).
    Refuses on zero (root / unknown / created-in-buffer element) or multiple
    owning memberships. The prior-less-ness comes from `session.modify_element`
    threading `prior_version=None` when the Session has no resolver — the
    production Session built in server.py's build_server() has no resolver,
    so this holds in practice; a resolver-backed Session would thread a real
    prior_version instead, an untested path for this verb.
    ponytail: O(n) membership scan per move, same as
    child discovery; index it if models outgrow pilot scale."""
    memberships = [
        el for el in api_client.get_elements(commit_id)
        if (el.get("ownedMemberElement") or {}).get("@id") == element_id
        and (el.get("owningRelatedElement") or {}).get("@id")
    ]
    if len(memberships) != 1:
        raise ValueError(
            f"expected exactly one owning membership for {element_id}, "
            f"found {len(memberships)}")
    membership = memberships[0]
    session.modify_element(membership["@id"], {
        "@type": membership["@type"],
        "owningRelatedElement": {"@id": new_owner},
        "ownedMemberElement": {"@id": element_id}})
    return {"membership": membership["@id"],
            "old_owner": (membership.get("owningRelatedElement") or {}).get("@id"),
            "new_owner": new_owner}
