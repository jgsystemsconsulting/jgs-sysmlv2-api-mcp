# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""Thin wrapper over the official sysml_v2_api_client (Task 5).

SPIKE ground truth (2026-07-02) baked in:
- Reads return RAW JSON, not typed models — the generated Element model drops
  declaredName and every SysML payload field, even via to_dict(). We read via
  call_api(..., _preload_content=False) and json.loads the bytes, building the
  GET paths ourselves rather than going through the typed ElementApi.
- Writes (POST /commits) are NEVER auto-retried: a lost response after the
  request went out is an ambiguous outcome (AmbiguousWrite); a 409 is a
  branch-head-advance conflict (CommitConflict). Both are distinct so the
  caller can react correctly.
"""
import json

import sysml_v2_api_client as sc
from sysml_v2_api_client.api.project_api import ProjectApi
from sysml_v2_api_client.rest import ApiException

from .config import Config


class AmbiguousWrite(Exception):
    """POST /commits outcome is unknown; caller must reconcile, never blind-retry."""


class CommitConflict(Exception):
    """POST /commits returned 409 (branch head advanced); buffer survives, re-review + retry (SC5)."""


def _raw_json(resp):
    """Decode a call_api(..., _preload_content=False) response into a dict/list.
    The response may be an object with .data or a (resp, status, headers) tuple,
    depending on the installed client version."""
    data = resp.data if hasattr(resp, "data") else resp[0].data
    return json.loads(data.decode())


class ApiClient:
    def __init__(self, cfg: Config):
        conf = sc.Configuration(host=cfg.base_url)
        if cfg.token:
            # Bearer auth for a secured endpoint; the local pilot has no auth,
            # so wiring is present but correctness never depends on it.
            conf.api_key["Authorization"] = cfg.token
            conf.api_key_prefix["Authorization"] = "Bearer"
        self._raw = sc.ApiClient(conf)
        self._project = cfg.project
        self._project_api = ProjectApi(self._raw)

    # --- reads: RAW JSON (full SysML fidelity), safe to retry (caller's policy) ---
    def list_projects(self) -> list:
        return _raw_json(self._raw.call_api("/projects", "GET", response_type=None, _preload_content=False))

    def _p(self, project):
        return project or self._project

    def get_element(self, commit_id: str, element_id: str, project: str | None = None) -> dict:
        path = f"/projects/{self._p(project)}/commits/{commit_id}/elements/{element_id}"
        return _raw_json(self._raw.call_api(path, "GET", response_type=None, _preload_content=False))

    def get_elements(self, commit_id: str, project: str | None = None) -> list:
        path = f"/projects/{self._p(project)}/commits/{commit_id}/elements"
        return _raw_json(self._raw.call_api(path, "GET", response_type=None, _preload_content=False))

    def get_commits(self, project: str | None = None) -> list:
        path = f"/projects/{self._p(project)}/commits"
        return _raw_json(self._raw.call_api(path, "GET", response_type=None, _preload_content=False))

    def resolve_head(self, project: str | None = None, branch_id: str | None = None) -> str | None:
        """Newest commit id, or None for an empty project. When branch_id is
        given, resolution short-circuits to that branch's head (D8: one
        authoritative GET — spike ground truth 12).
        BUG FIX (found during T1 implementation): the pilot's commit list is
        NOT reliably newest-first for commits created in rapid succession —
        `created` timestamps and `previousCommit` links are always correct,
        but list order can be wrong (confirmed: 5/8 trials wrong on two
        commits made back-to-back). Head is instead computed as the one
        commit that is nobody's previousCommit — i.e. no other commit in the
        list points to it as its parent. Falls back to commits[0] (old
        behaviour) if that's ambiguous (0 or 2+ such commits, e.g. once
        multiple branches exist — not a T1 scenario, but a safe fallback)."""
        if branch_id:
            # D8: one authoritative GET (spike ground truth 12)
            return (self.get_branch(branch_id, project).get("head") or {}).get("@id")
        commits = self.get_commits(project)
        if not commits:
            return None
        parented = {(c.get("previousCommit") or {}).get("@id") for c in commits}
        heads = [c["@id"] for c in commits if c["@id"] not in parented]
        return heads[0] if len(heads) == 1 else commits[0]["@id"]

    def get_project(self, project: str | None = None) -> dict:
        return _raw_json(self._raw.call_api(
            f"/projects/{self._p(project)}", "GET", response_type=None, _preload_content=False))

    def get_roots(self, commit_id: str, project: str | None = None) -> list:
        path = f"/projects/{self._p(project)}/commits/{commit_id}/roots"
        return _raw_json(self._raw.call_api(path, "GET", response_type=None, _preload_content=False))

    def get_relationships(self, commit_id: str, element_id: str,
                          direction: str = "both", project: str | None = None) -> list:
        # direction: in (element is target) | out (element is source) | both.
        # Pilot ground truth: matches ONLY explicit source/target arrays.
        path = f"/projects/{self._p(project)}/commits/{commit_id}/elements/{element_id}/relationships"
        return _raw_json(self._raw.call_api(
            path, "GET", query_params=[("direction", direction)],
            response_type=None, _preload_content=False))

    def get_commit(self, commit_id: str, project: str | None = None) -> dict:
        path = f"/projects/{self._p(project)}/commits/{commit_id}"
        return _raw_json(self._raw.call_api(path, "GET", response_type=None, _preload_content=False))

    def get_commit_changes(self, commit_id: str, project: str | None = None) -> list:
        # Full DataVersion records; no changeType discriminator exists on the
        # pilot (deletions are payload == null). No filter param on purpose.
        path = f"/projects/{self._p(project)}/commits/{commit_id}/changes"
        return _raw_json(self._raw.call_api(path, "GET", response_type=None, _preload_content=False))

    def get_branches(self, project: str | None = None) -> list:
        path = f"/projects/{self._p(project)}/branches"
        return _raw_json(self._raw.call_api(path, "GET", response_type=None, _preload_content=False))

    def get_branch(self, branch_id: str, project: str | None = None) -> dict:
        path = f"/projects/{self._p(project)}/branches/{branch_id}"
        return _raw_json(self._raw.call_api(path, "GET", response_type=None, _preload_content=False))

    def create_branch(self, name: str, head_commit_id: str, project: str | None = None) -> dict:
        path = f"/projects/{self._p(project)}/branches"
        body = {"@type": "Branch", "name": name, "head": {"@id": head_commit_id}}
        return _raw_json(self._raw.call_api(
            path, "POST", body=body, response_type=None, _preload_content=False))

    def delete_branch(self, branch_id: str, project: str | None = None) -> None:
        """Fire the DELETE and trust nothing: the pilot answers 500 even when
        the delete succeeded (spike ground truth 11). Callers verify via
        get_branches — see branch_tools.delete_branch_verified."""
        path = f"/projects/{self._p(project)}/branches/{branch_id}"
        try:
            self._raw.call_api(path, "DELETE", response_type=None, _preload_content=False)
        except ApiException:
            pass

    def get_tags(self, project: str | None = None) -> list:
        path = f"/projects/{self._p(project)}/tags"
        return _raw_json(self._raw.call_api(path, "GET", response_type=None, _preload_content=False))

    def create_tag(self, name: str, commit_id: str, project: str | None = None) -> dict:
        path = f"/projects/{self._p(project)}/tags"
        body = {"@type": "Tag", "name": name, "taggedCommit": {"@id": commit_id}}
        return _raw_json(self._raw.call_api(
            path, "POST", body=body, response_type=None, _preload_content=False))

    def create_project(self, name: str, description: str | None = None) -> dict:
        body = {"@type": "Project", "name": name}
        if description is not None:
            body["description"] = description          # round-trips (GT 17)
        return _raw_json(self._raw.call_api(
            "/projects", "POST", body=body, response_type=None, _preload_content=False))

    def put_project(self, project_id: str, body: dict) -> dict:
        """Caller must send a FULL readback echo — the pilot 500s minimal
        bodies (GT 18). See project_tools.update_project_fields."""
        return _raw_json(self._raw.call_api(
            f"/projects/{project_id}", "PUT", body=body,
            response_type=None, _preload_content=False))

    def delete_project(self, project_id: str) -> None:
        """Fire the DELETE and trust nothing: the pilot answers 500 even when
        the delete succeeded (GT 19). Callers verify via list_projects —
        see project_tools.delete_project_verified."""
        try:
            self._raw.call_api(f"/projects/{project_id}", "DELETE",
                               response_type=None, _preload_content=False)
        except ApiException:
            pass

    def query(self, commit_id: str, body: dict, project: str | None = None) -> list:
        # Raw JSON so payload fields survive (same fidelity concern as reads).
        # PRE-EXISTING BUG FIX (found during T1 implementation, ground truth 9 —
        # see "Pilot ground truths this plan encodes" in the T1 plan doc):
        # the real endpoint is project-scoped with commitId as a query param,
        # not /commits/{c}/query-results — the old path 404s on the live pilot.
        # QueryRequest also requires a "name" field (additionalProperties: false).
        path = f"/projects/{self._p(project)}/query-results"
        body = {**body, "name": body.get("name") or "query"}
        return _raw_json(self._raw.call_api(
            path, "POST", body=body, query_params=[("commitId", commit_id)],
            response_type=None, _preload_content=False))

    # --- write: NEVER auto-retried; ambiguous outcome or 409 surfaced distinctly ---
    def post_commit(self, commit_body: dict, branch_id: str | None = None) -> dict:
        path = f"/projects/{self._project}/commits"
        kwargs = {"body": commit_body, "response_type": None, "_preload_content": False}
        if branch_id:
            kwargs["query_params"] = [("branchId", branch_id)]   # spike ground truth 5
        try:
            return _raw_json(self._raw.call_api(path, "POST", **kwargs))
        except TimeoutError as e:
            # response lost after the request went out -> outcome unknown
            raise AmbiguousWrite(str(e)) from e
        except ApiException as e:
            if getattr(e, "status", None) == 409:
                raise CommitConflict(str(e)) from e   # branch head advanced (SC5)
            raise
