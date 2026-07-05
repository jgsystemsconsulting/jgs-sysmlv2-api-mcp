# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""Integration tests for the licence WRITE gate wired into server.py.

Exercises the central gate in ``server.dispatch(...)`` (the synchronous seam
the async ``call_tool`` handler wraps) end-to-end: the server loads the licence
ONCE at ``build_server()`` time into an in-memory state; WRITE-tier tools are
denied with the exact denial contract unless the licence tier unlocks writes,
while FREE reads/navigation always work and ``get_licence`` always reports the
truth (even when the licence is missing/invalid).

Everything is mocked -- no live SysML v2 pilot is needed, so these are NOT
marked ``@pytest.mark.integration`` (that marker is reserved for the live-pilot
suite). Licence files are minted with a LOCAL test keypair via the shared
``conftest.py`` helpers; the PRO test threads that test key through the
production ``load_licence`` seam by monkeypatching ``licence.load_licence`` --
the exact attribute ``server.py`` calls -- so the real embedded public key is
never needed and ``licence.py`` is never modified.
"""
from __future__ import annotations

import functools

import pytest

from jgs_sysmlv2_api_mcp import licence
from jgs_sysmlv2_api_mcp import server as server_module
from jgs_sysmlv2_api_mcp.api_client import ApiClient
from jgs_sysmlv2_api_mcp.server import _denial_message, build_server

from .conftest import REF_DATE

# --- The exact set of 15 WRITE-gated tools (spec section 2). ------------------
# One representative per gated category is also called out in individual tests,
# but we assert the full 15 here so a mis-tag anywhere is caught.
GATED_TOOLS = [
    "create_element", "modify_element", "delete_element", "delete_subtree",
    "create_relationship", "move_element", "stage_batch", "commit_changes",
    "create_branch", "delete_branch", "merge_branch", "create_tag",
    "create_project", "update_project", "delete_project",
]

# Representative minimal argument sets so each gated handler *would* run if the
# gate let it through. Under FREE mode the gate denies before any handler code
# executes, so these args are never actually consumed there; they matter only
# for the PRO path where we assert the gate did NOT block (the handler runs and
# reaches the mocked ApiClient / Session layer).
GATED_ARGS = {
    "create_element": {"type": "PartDefinition", "name": "X", "owner": "o1"},
    "modify_element": {"element_id": "e1", "changes": {"declaredName": "Y"}},
    "delete_element": {"element_id": "e1"},
    "delete_subtree": {"element_id": "e1"},
    "create_relationship": {"type": "Dependency", "source": "s1", "target": "t1"},
    "move_element": {"element_id": "e1", "new_owner": "o2", "commit_id": "c1"},
    "stage_batch": {"operations": []},
    "commit_changes": {"confirm": "tok"},
    "create_branch": {"name": "b", "head_commit_id": "c1"},
    "delete_branch": {"branch_id": "b1", "confirm": True},
    "merge_branch": {"source_branch_id": "s1", "target_branch_id": "t1", "confirm": True},
    "create_tag": {"name": "v1", "commit_id": "c1"},
    "create_project": {"name": "proj"},
    "update_project": {"project_id": "p1", "name": "renamed"},
    "delete_project": {"project_id": "p1", "confirm": True},
}

# A representative FREE read tool per "read/navigation" surface.
FREE_READ_TOOLS = ["list_projects", "get_commits", "get_project", "list_branches",
                   "list_tags", "ping", "stats"]


# --- Fixtures / helpers -------------------------------------------------------


@pytest.fixture()
def env(monkeypatch):
    """Standard server env + an isolated, empty licence search space.

    Neutralizes the exe-dir and home-dir search candidates so ONLY the env-var
    path (set per-test) can ever select a licence -- no stray real licence on
    the developer/CI machine can leak in.
    """
    monkeypatch.setenv("SYSMLV2_BASE_URL", "http://localhost:9000")
    monkeypatch.setenv("SYSMLV2_TOKEN", "secret-token")
    monkeypatch.setenv("SYSMLV2_PROJECT", "p")
    monkeypatch.delenv("JGS_V2_API_LICENCE_PATH", raising=False)
    # Neutralize exe-dir and home-dir candidates.
    monkeypatch.setattr(licence.sys, "argv", ["/nonexistent/no_exe_here"])
    monkeypatch.setattr(
        licence.Path, "home",
        staticmethod(lambda: licence.Path("/nonexistent/no_home_here")),
    )


def _pin_ref_date(monkeypatch, pub_b64):
    """Make ``build_server``'s ``licence.load_licence()`` use the test pubkey
    and a fixed reference date, without touching ``licence.py``.

    ``server.py`` calls ``licence.load_licence()`` with defaults; we swap that
    attribute for a partial that forwards ``public_key_b64`` + ``reference_date``
    into the real implementation. The real search-order / read logic still runs.
    """
    real = licence.load_licence
    patched = functools.partial(real, public_key_b64=pub_b64, reference_date=REF_DATE)
    monkeypatch.setattr(licence, "load_licence", patched)


def _mock_apiclient(monkeypatch):
    """Stub the ApiClient methods the FREE reads and PRO write-path touch, so
    no live pilot is needed. Returns a call-log list."""
    calls = []

    def rec(name, ret):
        def _fn(self, *a, **k):
            calls.append(name)
            return ret
        return _fn

    monkeypatch.setattr(ApiClient, "list_projects", rec("list_projects", []))
    monkeypatch.setattr(ApiClient, "get_commits", rec("get_commits", []))
    monkeypatch.setattr(ApiClient, "get_project", rec("get_project", {"defaultBranch": {"@id": "db"}}))
    monkeypatch.setattr(ApiClient, "get_branches", rec("get_branches", []))
    monkeypatch.setattr(ApiClient, "get_tags", rec("get_tags", []))
    return calls


# =============================================================================
# Scenario 1: No licence (FREE)
# =============================================================================


def test_no_licence_free_reads_succeed(env, monkeypatch):
    _mock_apiclient(monkeypatch)
    server = build_server()
    assert server.licence_state.valid is False
    assert server.licence_state.reason == "missing"

    # Representative reads succeed (they reach the mocked ApiClient, not the gate).
    assert server.dispatch("list_projects", {}) == []
    assert server.dispatch("get_commits", {}) == []
    assert server.dispatch("ping", {})["up"] is True
    assert isinstance(server.dispatch("stats", {}), dict)
    assert server.dispatch("list_branches", {}) == []
    assert server.dispatch("list_tags", {}) == []
    assert "defaultBranch" in server.dispatch("get_project", {})


@pytest.mark.parametrize("tool", GATED_TOOLS)
def test_no_licence_every_gated_tool_denied(env, monkeypatch, tool):
    """All 15 gated tools (covering every gated category: element-staging,
    commit, branch, tag, project) return the EXACT denial contract with
    reason=missing -- before any handler code runs."""
    _mock_apiclient(monkeypatch)
    server = build_server()

    with pytest.raises(PermissionError) as exc:
        server.dispatch(tool, GATED_ARGS[tool])
    assert str(exc.value) == _denial_message("missing")
    # sanity: the denial embeds the coarse reason code, nothing finer-grained.
    assert "licence required (missing):" in str(exc.value)
    assert "support@jgsystemsconsulting.com" in str(exc.value)


def test_no_licence_get_licence_reports_missing(env, monkeypatch):
    _mock_apiclient(monkeypatch)
    server = build_server()
    lic = server.dispatch("get_licence", {})
    assert lic["valid"] is False
    assert lic["reason"] == "missing"
    assert lic["tier"] is None
    assert lic["source"] is None
    # The internal `fields` dict must never leak into the public contract.
    assert "fields" not in lic


def test_write_tools_remain_visible_in_list_regardless_of_tier(env, monkeypatch):
    """Gating is invocation-only: write tools stay in the catalog even unlicensed."""
    _mock_apiclient(monkeypatch)
    server = build_server()
    visible = {t.name for t in server.tool_specs()}
    for tool in GATED_TOOLS:
        assert tool in visible, f"{tool} must stay visible in tools/list"
    assert "get_licence" in visible


# =============================================================================
# Scenario 2: Valid PRO licence
# =============================================================================


def test_valid_pro_licence_lifts_gate(env, monkeypatch, tmp_path, test_key, mint_licence):
    """A valid PRO licence (signed by the LOCAL test key, threaded through the
    real load_licence via the pubkey seam) lifts the gate: gated tools run and
    reach the (mocked) handler layer instead of being denied."""
    priv, pub = test_key
    lic_file = tmp_path / "valid.licence"
    lic_file.write_bytes(mint_licence(tier="pro", expires="2027-01-01"))
    monkeypatch.setenv("JGS_V2_API_LICENCE_PATH", str(lic_file))
    _pin_ref_date(monkeypatch, pub)

    _mock_apiclient(monkeypatch)
    # Stub the staging/session + write handler layers so the write handlers run
    # to completion without a live pilot. The assertion is "the gate did not
    # block", i.e. the real handler logic ran and hit these mocks.
    monkeypatch.setattr(server_module, "_create_element",
                        lambda session, **k: {"staged": "create", **k})
    monkeypatch.setattr(server_module, "delete_branch_verified",
                        lambda api, branch_id: {"deleted": True})
    monkeypatch.setattr(server_module, "squash_merge",
                        lambda api, s, t, description=None: {"outcome": "merged"})
    monkeypatch.setattr(server_module, "delete_project_verified",
                        lambda api, pid, configured: {"deleted": pid})
    monkeypatch.setattr(server_module, "update_project_fields",
                        lambda api, **k: {"updated": True})
    monkeypatch.setattr(ApiClient, "create_project", lambda self, name, desc=None: {"@id": "np"})
    monkeypatch.setattr(ApiClient, "resolve_head", lambda self, project=None, branch_id=None: "head-c")
    monkeypatch.setattr(ApiClient, "create_branch", lambda self, name, head: {"@id": "nb"})
    monkeypatch.setattr(ApiClient, "create_tag", lambda self, name, commit_id: {"@id": "nt"})

    server = build_server()
    assert server.licence_state.valid is True
    assert server.licence_state.tier == "pro"

    # Representative gated tool per category runs (no PermissionError raised).
    assert server.dispatch("create_element", GATED_ARGS["create_element"])["staged"] == "create"
    assert server.dispatch("create_branch", GATED_ARGS["create_branch"]) == {"@id": "nb"}
    assert server.dispatch("create_tag", GATED_ARGS["create_tag"]) == {"@id": "nt"}
    assert server.dispatch("create_project", GATED_ARGS["create_project"]) == {"@id": "np"}
    assert server.dispatch("delete_branch", GATED_ARGS["delete_branch"]) == {"deleted": True}
    assert server.dispatch("merge_branch", GATED_ARGS["merge_branch"]) == {"outcome": "merged"}
    assert server.dispatch("delete_project", GATED_ARGS["delete_project"]) == {"deleted": "p1"}


def test_valid_pro_get_licence_reports_pro(env, monkeypatch, tmp_path, test_key, mint_licence):
    priv, pub = test_key
    lic_file = tmp_path / "valid.licence"
    lic_file.write_bytes(mint_licence(tier="pro", expires="2027-01-01",
                                      customer="Acme Systems Ltd."))
    monkeypatch.setenv("JGS_V2_API_LICENCE_PATH", str(lic_file))
    _pin_ref_date(monkeypatch, pub)
    _mock_apiclient(monkeypatch)

    server = build_server()
    lic = server.dispatch("get_licence", {})
    assert lic["valid"] is True
    assert lic["tier"] == "pro"
    assert lic["reason"] == "ok"
    assert lic["customer"] == "Acme Systems Ltd."
    assert lic["source"] == str(lic_file)
    assert "fields" not in lic


def test_valid_free_tier_licence_still_denies_writes(env, monkeypatch, tmp_path, test_key, mint_licence):
    """A cryptographically VALID licence whose tier is `free` must still deny
    writes (free -> READ; only pro/enterprise/academic unlock writes)."""
    priv, pub = test_key
    lic_file = tmp_path / "free.licence"
    lic_file.write_bytes(mint_licence(tier="free", expires="2027-01-01"))
    monkeypatch.setenv("JGS_V2_API_LICENCE_PATH", str(lic_file))
    _pin_ref_date(monkeypatch, pub)
    _mock_apiclient(monkeypatch)

    server = build_server()
    assert server.licence_state.valid is True
    assert server.licence_state.tier == "free"
    with pytest.raises(PermissionError) as exc:
        server.dispatch("create_element", GATED_ARGS["create_element"])
    # A valid free licence's reason is "ok", so the denial code is "ok" here.
    assert str(exc.value) == _denial_message("ok")


# =============================================================================
# Scenario 3: Search-order precedence (server picks up env-var override)
# =============================================================================


def test_env_var_licence_is_used_end_to_end(env, monkeypatch, tmp_path, test_key, mint_licence):
    """Whatever load_licence selects (here: the env-var file), the SERVER uses
    that result end-to-end -- env-var override -> server picks it up -> gate
    behaves accordingly. (Raw exe-dir/home-dir precedence is covered at the
    licence.py unit layer; this asserts the server-relevant lever works.)"""
    priv, pub = test_key
    lic_file = tmp_path / "env_selected.licence"
    lic_file.write_bytes(mint_licence(tier="enterprise", expires="2027-01-01"))
    monkeypatch.setenv("JGS_V2_API_LICENCE_PATH", str(lic_file))
    _pin_ref_date(monkeypatch, pub)
    _mock_apiclient(monkeypatch)
    monkeypatch.setattr(server_module, "_create_element",
                        lambda session, **k: {"staged": "create", **k})

    server = build_server()
    assert server.licence_state.source == str(lic_file)
    assert server.licence_state.tier == "enterprise"
    # enterprise unlocks writes (functionally == pro at launch).
    assert server.dispatch("create_element", GATED_ARGS["create_element"])["staged"] == "create"


# =============================================================================
# Scenario 4: Invalid file at higher precedence does NOT fall through
# =============================================================================


def test_invalid_env_licence_does_not_fall_through(env, monkeypatch, tmp_path, test_key, mint_licence):
    """The env-var (highest precedence) file is a tampered/bad-signature file;
    a perfectly valid file exists at the lower home-dir location. The server
    must end up FREE with the bad file's specific reason (bad_signature), NOT
    silently fall through to the valid one."""
    priv, pub = test_key

    # Highest precedence: a validly-structured licence whose signature is broken.
    good_bytes = mint_licence(tier="pro", expires="2027-01-01")
    tampered = bytearray(good_bytes)
    idx = good_bytes.index(b"tier=pro")
    tampered[idx + 5] ^= 0x01  # flip a payload byte -> signature mismatch
    bad_file = tmp_path / "bad.licence"
    bad_file.write_bytes(bytes(tampered))
    monkeypatch.setenv("JGS_V2_API_LICENCE_PATH", str(bad_file))

    # Lower precedence (home-dir): a valid file that must NOT be reached.
    home = tmp_path / "home"
    (home / ".jgs-sysmlv2-api").mkdir(parents=True)
    good_file = home / ".jgs-sysmlv2-api" / licence.LICENCE_FILENAME
    good_file.write_bytes(good_bytes)
    monkeypatch.setattr(licence.Path, "home", staticmethod(lambda: home))
    _pin_ref_date(monkeypatch, pub)
    _mock_apiclient(monkeypatch)

    server = build_server()
    assert server.licence_state.source == str(bad_file)
    assert server.licence_state.valid is False
    assert server.licence_state.reason == "bad_signature"

    lic = server.dispatch("get_licence", {})
    assert lic["reason"] == "bad_signature"
    with pytest.raises(PermissionError) as exc:
        server.dispatch("create_element", GATED_ARGS["create_element"])
    assert str(exc.value) == _denial_message("bad_signature")


# =============================================================================
# Scenario 5: Unreadable licence file -> FREE, reason unreadable, no crash
# =============================================================================


def test_unreadable_licence_is_free_no_crash(env, monkeypatch, tmp_path, test_key, mint_licence):
    """An existing file that cannot be read (simulated via read_bytes raising
    PermissionError, which is portable across Windows/POSIX unlike os.chmod)
    -> server builds successfully in FREE mode with reason `unreadable`."""
    priv, pub = test_key
    lic_file = tmp_path / "locked.licence"
    lic_file.write_bytes(mint_licence(tier="pro", expires="2027-01-01"))
    monkeypatch.setenv("JGS_V2_API_LICENCE_PATH", str(lic_file))
    _pin_ref_date(monkeypatch, pub)
    _mock_apiclient(monkeypatch)

    real_read_bytes = licence.Path.read_bytes

    def guarded_read_bytes(self):
        if str(self) == str(lic_file):
            raise PermissionError("simulated locked file")
        return real_read_bytes(self)

    monkeypatch.setattr(licence.Path, "read_bytes", guarded_read_bytes)

    # Must not raise / exit -- the whole point of "never a crash".
    server = build_server()
    assert server.licence_state.valid is False
    assert server.licence_state.reason == "unreadable"
    assert server.licence_state.source == str(lic_file)

    lic = server.dispatch("get_licence", {})
    assert lic["reason"] == "unreadable"
    with pytest.raises(PermissionError) as exc:
        server.dispatch("create_element", GATED_ARGS["create_element"])
    assert str(exc.value) == _denial_message("unreadable")


# =============================================================================
# Scenario 6: Licence deleted mid-session has no live effect (load-once)
# =============================================================================


def test_licence_deleted_mid_session_has_no_live_effect(env, monkeypatch, tmp_path, test_key, mint_licence):
    """Build the server with a valid PRO licence present (gated tools succeed),
    then DELETE the licence file from disk and call a gated tool AGAIN on the
    SAME already-built server -> still succeeds. Proves load_licence() runs once
    at build_server() time and the result is cached in a closure, never re-read
    during the process lifetime (spec: load-once, not live re-validation)."""
    priv, pub = test_key
    lic_file = tmp_path / "valid.licence"
    lic_file.write_bytes(mint_licence(tier="pro", expires="2027-01-01"))
    monkeypatch.setenv("JGS_V2_API_LICENCE_PATH", str(lic_file))
    _pin_ref_date(monkeypatch, pub)
    _mock_apiclient(monkeypatch)
    monkeypatch.setattr(server_module, "_create_element",
                        lambda session, **k: {"staged": "create", **k})

    server = build_server()
    assert server.licence_state.tier == "pro"
    # Works before deletion.
    assert server.dispatch("create_element", GATED_ARGS["create_element"])["staged"] == "create"

    # Delete the file mid-session.
    lic_file.unlink()
    assert not lic_file.exists()

    # Still works on the SAME server object -- the cached in-memory tier holds.
    assert server.dispatch("create_element", GATED_ARGS["create_element"])["staged"] == "create"
    # And get_licence still reports the cached valid state (no re-read).
    lic = server.dispatch("get_licence", {})
    assert lic["valid"] is True
    assert lic["tier"] == "pro"
