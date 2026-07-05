# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""Task 14 — server wiring + MCP tool registration.

Builds the MCP `Server`, wires config/logging/ApiClient/Session/Metrics, and
registers the 14 spec tools as thin adapters over the tested modules from
Tasks 5-13. `commit_changes` carries the only real control flow (the
SPIKE-corrected commit flow: build_commit_body returns a BODY-ONLY dict, the
server assigns the commit id from the raw POST response, and reconcile keys
on branch head-advance rather than a client-minted commit id).

Registration mechanism: the installed `mcp` SDK (>=1.0, lowlevel `Server`)
exposes a single `@server.list_tools()` handler returning `list[types.Tool]`
and a single `@server.call_tool()` handler dispatching by name — there is no
per-tool decorator and no built-in name introspection. We keep our own
`_TOOLS: dict[str, dict]` registry (name -> {tool, handler}) built by
`_register(...)`, and derive both MCP handlers plus a `tool_names()` helper
from it, so the registered names are stable and directly testable.
"""
import json
import logging

import mcp.types as types
from mcp.server import Server

from . import licence
from .api_client import AmbiguousWrite, ApiClient, CommitConflict
from .config import load_config
from .logging_setup import configure_logging
from .metrics import Metrics
from .reconcile import reconcile
from .session import Session
from .tools.author_tools import (
    create_element as _create_element,
    create_relationship as _create_relationship,
    delete_element as _delete_element,
    delete_subtree as _delete_subtree,
    modify_element as _modify_element,
    move_element as _move_element,
)
from .tools.branch_tools import delete_branch_verified, squash_merge
from .tools.commit_tools import build_commit_body
from .tools.nav_tools import (
    child_ids,
    filter_root_ids as _filter_root_ids,
    find_by_name as _find_by_name,
    get_children as _get_children,
    related_ids,
    traverse,
)
from .tools.project_tools import delete_project_verified, update_project_fields
from .tools.read_tools import diff_commits as _diff_commits, query_elements_page

_EMPTY_SCHEMA = {"type": "object", "properties": {}}

log = logging.getLogger(__name__)

#: Tiers that unlock WRITE-gated (authoring) tools. FREE and any invalid/missing
#: licence state map outside this set and are denied (spec section 1: free -> READ;
#: pro/enterprise/academic -> WRITE).
_WRITE_TIERS = frozenset({"pro", "enterprise", "academic"})


def _denial_message(reason_code):
    """The exact byte-for-byte denial contract (spec section 2)."""
    return (
        f"licence required ({reason_code}): authoring tools need a valid "
        "sysmlv2-api-pro licence. Licences load at server start - restart your "
        "MCP client after installing one. Contact support@jgsystemsconsulting.com"
    )


def build_server():
    cfg = load_config()
    configure_logging(destination="stderr", secrets=[cfg.token])

    # Load the licence ONCE at startup; the file is never re-read during the
    # process lifetime (spec section 2 "load-once, not live re-validation").
    # Missing / invalid / tampered / expired -> FREE mode, never a crash.
    licence_state = licence.load_licence()
    if licence_state.valid:
        log.warning(
            "licence: valid (tier=%s, customer=%s, expires=%s, source=%s)",
            licence_state.tier, licence_state.customer,
            licence_state.expires, licence_state.source,
        )
    else:
        log.warning(
            "licence: FREE mode (%s) - authoring tools are disabled; "
            "install a valid sysmlv2-api-pro licence and restart your MCP client",
            licence_state.reason,
        )
    if licence_state.expires_soon:
        log.warning(
            "licence: expires in %s day(s) (%s) - renew soon; contact "
            "support@jgsystemsconsulting.com",
            licence_state.days_remaining, licence_state.expires,
        )

    api = ApiClient(cfg)
    session = Session(project=cfg.project, buffer_cap=cfg.buffer_cap,
                       token_ttl=cfg.token_ttl_seconds, branch=cfg.branch)
    metrics = Metrics()
    server = Server("jgs-sysmlv2-api-mcp")

    default_branch_id = None

    def _active_branch_id():
        """Session branch if set, else the project's default branch id
        (lazily resolved once — a project's default branch never changes).
        Makes ALL head resolution branch-authoritative (GET /branches/{b})
        instead of relying on project-wide commit-list heuristics.
        The unlocked nonlocal cache is race-free only because MCP tool
        handlers run synchronously on one asyncio event loop (stdio_server)."""
        nonlocal default_branch_id
        if session.branch:
            return session.branch
        if default_branch_id is None:
            default_branch_id = (api.get_project().get("defaultBranch") or {}).get("@id")
        return default_branch_id

    tools: dict[str, dict] = {}

    def register(name, description, input_schema, handler, tier="free"):
        tools[name] = {
            "tool": types.Tool(name=name, description=description, inputSchema=input_schema),
            "handler": handler,
            "tier": tier,
        }

    def _commit_or_head(args):
        cid = args.get("commit_id")
        if cid:
            return cid
        head = api.resolve_head(branch_id=_active_branch_id())
        if head is None:
            raise ValueError("project has no commits yet; supply commit_id after the first commit")
        return head

    # --- read tools (raw-JSON via ApiClient) ---
    def list_projects(args):
        return api.list_projects()

    def get_commits(args):
        return api.get_commits()

    def get_element(args):
        return api.get_element(_commit_or_head(args), args["element_id"])

    def query_elements(args):
        return query_elements_page(
            api, _commit_or_head(args), args.get("filter"),
            cursor=args.get("cursor"), page_size=args.get("page_size", 50),
        )

    register("list_projects", "List projects visible to this API endpoint.",
              _EMPTY_SCHEMA, list_projects)
    register("get_commits", "List commits for the configured project. Order is not guaranteed to be newest-first (use resolve_head/get_commit for the actual head).",
              _EMPTY_SCHEMA, get_commits)
    register("get_element", "Fetch a single element (raw JSON, full fidelity) at a commit. commit_id defaults to the branch head.",
              {"type": "object", "properties": {
                  "commit_id": {"type": "string"}, "element_id": {"type": "string"}},
               "required": ["element_id"]}, get_element)
    register("query_elements", "Query elements at a commit with opaque-cursor pagination. commit_id defaults to the branch head.",
              {"type": "object", "properties": {
                  "commit_id": {"type": "string"}, "filter": {"type": "object"},
                  "cursor": {"type": "string"}, "page_size": {"type": "integer"}},
               "required": []}, query_elements)

    # --- author tools (stage-only mutation surface over Session) ---
    def create_element(args):
        return _create_element(session, type=args["type"], name=args["name"], owner=args["owner"])

    def modify_element(args):
        return _modify_element(session, args["element_id"], args["changes"])

    def delete_element(args):
        return _delete_element(session, args["element_id"])

    def delete_subtree(args):
        return _delete_subtree(session, args["element_id"])

    register("create_element", "Stage creation of a new element under an owner (buffer-only).",
              {"type": "object", "properties": {
                  "type": {"type": "string"}, "name": {"type": "string"}, "owner": {"type": "string"}},
               "required": ["type", "name", "owner"]}, create_element, tier="write")
    register("modify_element", "Stage a modification to an existing element (buffer-only).",
              {"type": "object", "properties": {
                  "element_id": {"type": "string"}, "changes": {"type": "object"}},
               "required": ["element_id", "changes"]}, modify_element, tier="write")
    register("delete_element", "Stage deletion of a single element (buffer-only; refuses if it owns children).",
              {"type": "object", "properties": {"element_id": {"type": "string"}},
               "required": ["element_id"]}, delete_element, tier="write")
    register("delete_subtree", "Stage deletion of an element and its owned subtree (buffer-only).",
              {"type": "object", "properties": {"element_id": {"type": "string"}},
               "required": ["element_id"]}, delete_subtree, tier="write")

    # --- T4 authoring extensions ---
    def create_relationship(args):
        return _create_relationship(session, type=args["type"], source=args["source"],
                                    target=args["target"], owner=args.get("owner"),
                                    properties=args.get("properties"))

    def move_element(args):
        return _move_element(api, session, args["element_id"], args["new_owner"],
                             _commit_or_head(args))

    def stage_batch(args):
        return {"staged": session.stage_batch(args["operations"])}

    register("create_relationship", "Stage a typed relationship (buffer-only). Sets explicit source/target plus the type's concrete end fields (Subclassification, Specialization, Subsetting, Redefinition, FeatureTyping, Dependency); other types take concrete ends via properties.",
             {"type": "object", "properties": {
                 "type": {"type": "string"}, "source": {"type": "string"},
                 "target": {"type": "string"}, "owner": {"type": "string"},
                 "properties": {"type": "object"}},
              "required": ["type", "source", "target"]}, create_relationship, tier="write")
    register("move_element", "Stage a rehome of an element to a new owner (buffer-only; modifies its OwningMembership at the commit). commit_id defaults to the branch head.",
             {"type": "object", "properties": {
                 "element_id": {"type": "string"}, "new_owner": {"type": "string"},
                 "commit_id": {"type": "string"}},
              "required": ["element_id", "new_owner"]}, move_element, tier="write")
    register("stage_batch", "Stage many operations atomically (all-or-nothing, buffer-only). Ops: {op: create|relate|modify|delete, ...}; create ops accept a caller-minted element_id so later ops in the batch can reference it.",
             {"type": "object", "properties": {
                 "operations": {"type": "array", "items": {"type": "object"}}},
              "required": ["operations"]}, stage_batch, tier="write")

    # --- review / commit / discard ---
    def review_changes(args):
        return session.review_changes()

    def commit_changes(args):
        message = args.get("message")
        confirm = args["confirm"]
        snapshot = session.begin_commit(confirm)          # TokenError if bad
        head = api.resolve_head(branch_id=_active_branch_id())
        body = build_commit_body(snapshot, previous_commit=head)   # BODY-ONLY dict
        if message:
            body["description"] = message
        metrics.incr("commits_attempted")
        try:
            # session.branch=None omits ?branchId= -> pilot writes its default branch;
            # _active_branch_id() above resolves that same default explicitly for
            # head/reconcile. Two expressions, same target branch, kept in sync.
            result = api.post_commit(body, branch_id=session.branch)  # RLock not held across this
            session.finish_commit(snapshot)
            metrics.incr("commits_succeeded")
            return {"commit_id": result.get("@id")}        # server-assigned id from raw JSON
        except CommitConflict:
            session.abort_commit()
            metrics.incr("commits_failed")
            return {"outcome": "conflict",
                    "hint": "branch head advanced; re-review and commit again"}
        except AmbiguousWrite:
            session.abort_commit()
            metrics.incr("commits_failed")
            return reconcile(api.get_commits, previous_commit=head,
                             resolve_head=lambda: api.resolve_head(
                                 branch_id=_active_branch_id()))
        except Exception:
            session.abort_commit()
            metrics.incr("commits_failed")
            raise

    def discard_changes(args):
        session.discard()
        return {"outcome": "discarded"}

    register("review_changes", "Return the staged ops + a confirm token (must be reviewed before commit).",
              _EMPTY_SCHEMA, review_changes)
    register("commit_changes", "Commit the staged buffer; requires a fresh confirm token.",
              {"type": "object", "properties": {
                  "message": {"type": "string"}, "confirm": {"type": "string"}},
               "required": ["confirm"]}, commit_changes, tier="write")
    register("discard_changes", "Discard the staged buffer without committing.",
              _EMPTY_SCHEMA, discard_changes)

    # --- nav / health / stats ---
    def nav_traverse(args):
        commit_id = _commit_or_head(args)
        root = args["root"]
        max_depth = args.get("max_depth", 25)
        follow = args.get("follow_relationships", False)

        def _children(node):
            ids = child_ids(api, commit_id, node)
            if follow:
                ids = ids + related_ids(api, commit_id, node)
            return ids

        result = traverse(root, _children, max_depth=max_depth)
        if args.get("include_names"):
            elements = {}
            for vid in result["visited"]:
                el = api.get_element(commit_id, vid)
                elements[vid] = {"name": el.get("declaredName") or el.get("name"),
                                 "type": el.get("@type")}
            result["elements"] = elements
        return result

    def ping(args):
        commits = api.get_commits()
        return {"up": True, "api_version": getattr(api, "api_version", None),
                "commit_count": len(commits)}

    def stats(args):
        return metrics.snapshot()

    def get_licence(args):
        # Served entirely from the in-memory state loaded once at startup; no
        # file re-read. Always available (FREE tier) and intentionally works
        # even when the licence is invalid/missing so the user can see WHY
        # (the renewal-visibility channel, spec section 2). The internal
        # `fields` dict is not part of the public contract and is omitted.
        return {
            "valid": licence_state.valid,
            "reason": licence_state.reason,
            "tier": licence_state.tier,
            "customer": licence_state.customer,
            "expires": licence_state.expires,
            "days_remaining": licence_state.days_remaining,
            "expires_soon": licence_state.expires_soon,
            "seats": licence_state.seats,
            "features": licence_state.features,
            "source": licence_state.source,
        }

    register("nav_traverse", "Traverse owned-member hierarchy from a root element (cycle-safe). commit_id defaults to the branch head.",
              {"type": "object", "properties": {
                  "commit_id": {"type": "string"}, "root": {"type": "string"},
                  "max_depth": {"type": "integer"},
                  "follow_relationships": {"type": "boolean", "description": "follow outgoing typed relationships in addition to containment — note a node reachable via both a containment path and a relationship path re-encounters and registers as `cycle_detected`/`cycle_nodes`, even in an acyclic diamond; treat that signal as 'reached twice', not necessarily a true cycle"},
                  "include_names": {"type": "boolean", "description": "include a `{id: {name, type}}` map for visited elements"}},
               "required": ["root"]}, nav_traverse)
    register("ping", "Minimal liveness probe: confirms the endpoint is reachable.",
              _EMPTY_SCHEMA, ping)
    register("stats", "Return a snapshot of server metrics counters.",
              _EMPTY_SCHEMA, stats)
    register("get_licence", "Report the current licence state (valid, reason, tier, customer, expires, days_remaining, expires_soon, seats, features, source) from the in-memory state loaded once at server start. Always available; shows why authoring is locked when unlicensed.",
              _EMPTY_SCHEMA, get_licence)

    # --- T1 navigation reads ---
    def get_project(args):
        return api.get_project(args.get("project_id"))

    def get_root_elements(args):
        # ponytail: two HTTP calls (roots + full element scan) because the
        # pilot's /roots doesn't filter owned elements server-side — see
        # filter_root_ids in nav_tools.py.
        commit_id = _commit_or_head(args)
        candidates = api.get_roots(commit_id)
        root_ids = set(_filter_root_ids(api, commit_id, candidates))
        return [c for c in candidates if c["@id"] in root_ids]

    def get_relationships(args):
        return api.get_relationships(_commit_or_head(args), args["element_id"],
                                     direction=args.get("direction", "both"))

    def get_children(args):
        return _get_children(api, _commit_or_head(args), args["element_id"])

    def find_by_name(args):
        return _find_by_name(api, _commit_or_head(args), args["name"],
                             type=args.get("type"))

    # commit_id is NOT defaulted here (no _commit_or_head) — these fetch one
    # specific named commit by definition, unlike the browsing reads above.
    def get_commit(args):
        return api.get_commit(args["commit_id"])

    def get_commit_changes(args):
        return api.get_commit_changes(args["commit_id"])

    def diff_commits(args):
        return _diff_commits(api, args["base_commit"], args["compare_commit"])

    register("get_project", "Project metadata (name, description, default branch). Optional project_id overrides the configured project.",
             {"type": "object", "properties": {"project_id": {"type": "string"}}}, get_project)
    register("get_root_elements", "Root (unowned) elements at a commit: the entry point into a model. Filtered client-side (the pilot's /roots does not exclude owned elements). commit_id defaults to the branch head.",
             {"type": "object", "properties": {"commit_id": {"type": "string"}}}, get_root_elements)
    register("get_relationships", "Typed relationship elements touching an element (matches explicit source/target). direction: in|out|both. commit_id defaults to head.",
             {"type": "object", "properties": {
                 "commit_id": {"type": "string"}, "element_id": {"type": "string"},
                 "direction": {"type": "string", "enum": ["in", "out", "both"]}},
              "required": ["element_id"]}, get_relationships)
    register("get_children", "One level of owned children with id/name/type. commit_id defaults to head.",
             {"type": "object", "properties": {
                 "commit_id": {"type": "string"}, "element_id": {"type": "string"}},
              "required": ["element_id"]}, get_children)
    register("find_by_name", "Find elements by declaredName, optional type filter. commit_id defaults to head.",
             {"type": "object", "properties": {
                 "commit_id": {"type": "string"}, "name": {"type": "string"},
                 "type": {"type": "string"}},
              "required": ["name"]}, find_by_name)
    register("get_commit", "Fetch a single commit record (previousCommit, description, created).",
             {"type": "object", "properties": {"commit_id": {"type": "string"}},
              "required": ["commit_id"]}, get_commit)
    register("get_commit_changes", "Full DataVersion change records of a commit (deletions have payload null).",
             {"type": "object", "properties": {"commit_id": {"type": "string"}},
              "required": ["commit_id"]}, get_commit_changes)
    register("diff_commits", "Diff two commits -> {created, deleted, modified} element-id lists (client-side; pilot lacks native diff).",
             {"type": "object", "properties": {
                 "base_commit": {"type": "string"}, "compare_commit": {"type": "string"}},
              "required": ["base_commit", "compare_commit"]}, diff_commits)

    # --- T2 versioning lifecycle ---
    def list_branches(args):
        return api.get_branches(args.get("project_id"))

    def create_branch(args):
        head = args.get("head_commit_id") or api.resolve_head(branch_id=_active_branch_id())
        if head is None:
            raise ValueError("project has no commits yet; nothing to branch from")
        return api.create_branch(args["name"], head)

    def delete_branch(args):
        if args.get("confirm") is not True:
            raise ValueError("delete_branch is destructive; pass confirm: true")
        return delete_branch_verified(api, args["branch_id"])

    def merge_branch(args):
        if args.get("confirm") is not True:
            raise ValueError("merge_branch writes to the target branch; pass confirm: true")
        try:
            return squash_merge(api, args["source_branch_id"], args["target_branch_id"],
                                description=args.get("description"))
        except CommitConflict:
            # target branch head advanced between the diff and the replay commit
            return {"outcome": "conflict",
                    "hint": "target branch head advanced; re-run merge_branch"}
        except AmbiguousWrite:
            return {"outcome": "error",
                    "reason": "merge commit response lost after send; verify target branch head before retrying"}

    def set_branch(args):
        branch_id = args["branch_id"]
        api.get_branch(branch_id)              # 404s on an unknown branch BEFORE retargeting
        session.set_branch(branch_id)          # StagingError if staged work exists (D6)
        return {"branch": branch_id}

    def list_tags(args):
        return api.get_tags(args.get("project_id"))

    def create_tag(args):
        commit_id = args.get("commit_id") or api.resolve_head(branch_id=_active_branch_id())
        if commit_id is None:
            raise ValueError("project has no commits yet; nothing to tag")
        return api.create_tag(args["name"], commit_id)

    register("list_branches", "List branches (id, name, head commit). Optional project_id overrides the configured project.",
             {"type": "object", "properties": {"project_id": {"type": "string"}}}, list_branches)
    register("create_branch", "Create a branch. head_commit_id defaults to the session branch head.",
             {"type": "object", "properties": {
                 "name": {"type": "string"}, "head_commit_id": {"type": "string"}},
              "required": ["name"]}, create_branch, tier="write")
    register("delete_branch", "Delete a branch (destructive; requires confirm: true). Outcome is verified via the branch list; the default branch is refused.",
             {"type": "object", "properties": {
                 "branch_id": {"type": "string"}, "confirm": {"type": "boolean"}},
              "required": ["branch_id", "confirm"]}, delete_branch, tier="write")
    register("merge_branch", "Squash-merge a source branch onto a target branch as one commit (requires confirm: true). Refuses with conflicting element ids if both branches changed the same element.",
             {"type": "object", "properties": {
                 "source_branch_id": {"type": "string"},
                 "target_branch_id": {"type": "string"},
                 "description": {"type": "string"}, "confirm": {"type": "boolean"}},
              "required": ["source_branch_id", "target_branch_id", "confirm"]}, merge_branch, tier="write")
    register("set_branch", "Retarget this session at a branch: staged commits and default read head follow it. Refused while staged work exists.",
             {"type": "object", "properties": {"branch_id": {"type": "string"}},
              "required": ["branch_id"]}, set_branch)
    register("list_tags", "List tags (name, tagged commit). Optional project_id overrides the configured project.",
             {"type": "object", "properties": {"project_id": {"type": "string"}}}, list_tags)
    register("create_tag", "Tag a commit (checkpoint). commit_id defaults to the session branch head.",
             {"type": "object", "properties": {
                 "name": {"type": "string"}, "commit_id": {"type": "string"}},
              "required": ["name"]}, create_tag, tier="write")

    # --- T3 project lifecycle ---
    def create_project(args):
        return api.create_project(args["name"], args.get("description"))

    def update_project(args):
        return update_project_fields(api, project_id=args.get("project_id"),
                                     name=args.get("name"),
                                     description=args.get("description"))

    def delete_project(args):
        if args.get("confirm") is not True:
            raise ValueError("delete_project is destructive; pass confirm: true")
        return delete_project_verified(api, args["project_id"], cfg.project)

    register("create_project", "Create a project (name, optional description). The session stays bound to its configured project.",
             {"type": "object", "properties": {
                 "name": {"type": "string"}, "description": {"type": "string"}},
              "required": ["name"]}, create_project, tier="write")
    register("update_project", "Rename or re-describe a project. project_id defaults to the configured project. Only provided fields change.",
             {"type": "object", "properties": {
                 "project_id": {"type": "string"}, "name": {"type": "string"},
                 "description": {"type": "string"}}}, update_project, tier="write")
    register("delete_project", "Delete a project (destructive; requires confirm: true). The session's configured project is refused; outcome is verified via the project list.",
             {"type": "object", "properties": {
                 "project_id": {"type": "string"}, "confirm": {"type": "boolean"}},
              "required": ["project_id", "confirm"]}, delete_project, tier="write")

    @server.list_tools()
    async def _list_tools():
        # Write tools stay VISIBLE regardless of tier; only invocation is gated
        # (spec section 2: static tool surface, honest catalog).
        return [entry["tool"] for entry in tools.values()]

    def dispatch(name, arguments):
        """Gate + invoke a tool by name (synchronous; the testable seam).

        WRITE-tier tools require a licence whose canonical tier unlocks writes
        (pro / enterprise / academic). FREE or invalid/missing licences raise
        ``PermissionError`` carrying the exact denial contract; the MCP SDK's
        ``call_tool`` wrapper turns any raised exception into an
        ``isError: true`` tool result whose text is ``str(exc)``.
        """
        entry = tools.get(name)
        if entry is None:
            raise ValueError(f"unknown tool: {name}")
        if entry["tier"] == "write" and licence_state.tier not in _WRITE_TIERS:
            raise PermissionError(_denial_message(licence_state.reason))
        return entry["handler"](arguments or {})

    @server.call_tool()
    async def _call_tool(name, arguments):
        result = dispatch(name, arguments)
        return {"result": json.loads(json.dumps(result, default=str))}

    server.dispatch = dispatch
    server.licence_state = licence_state
    server.tool_names = lambda: set(tools.keys())
    server.tool_specs = lambda: [t["tool"] for t in tools.values()]
    server._tools = tools   # exposed for tests/introspection
    return server


async def main():
    from mcp.server.stdio import stdio_server

    server = build_server()
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())
