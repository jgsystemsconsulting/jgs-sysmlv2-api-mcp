# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
import pytest

from jgs_sysmlv2_api_mcp.session import Session, TokenError


class FakeClock:
    def __init__(self): self.t = 1000.0
    def now(self): return self.t
    def advance(self, dt): self.t += dt


def test_review_issues_token_commit_consumes_it():
    clk = FakeClock()
    s = Session(project="p", buffer_cap=100, clock=clk.now, token_ttl=60)
    s.create_element(type="PartDefinition", name="A", owner="root")
    tok = s.review_changes()["confirm_token"]
    s.verify_and_consume(tok)   # no raise
    with pytest.raises(TokenError, match="consumed"):
        s.verify_and_consume(tok)   # single-use


def test_missing_and_malformed_token_rejected():
    s = Session(project="p", buffer_cap=100)
    s.create_element(type="PartDefinition", name="A", owner="root")
    s.review_changes()
    with pytest.raises(TokenError, match="missing or unknown"):
        s.verify_and_consume(None)
    with pytest.raises(TokenError, match="missing or unknown"):
        s.verify_and_consume("not-a-real-token")


def test_expired_token_rejected():
    clk = FakeClock()
    s = Session(project="p", buffer_cap=100, clock=clk.now, token_ttl=60)
    s.create_element(type="PartDefinition", name="A", owner="root")
    tok = s.review_changes()["confirm_token"]
    clk.advance(61)
    with pytest.raises(TokenError, match="expired"):
        s.verify_and_consume(tok)


def test_staging_after_review_invalidates_token():
    s = Session(project="p", buffer_cap=100)
    s.create_element(type="PartDefinition", name="A", owner="root")
    tok = s.review_changes()["confirm_token"]
    s.create_element(type="PartDefinition", name="B", owner="root")   # mutate buffer
    with pytest.raises(TokenError, match="fingerprint"):
        s.verify_and_consume(tok)


def test_finish_commit_preserves_ops_staged_during_post():
    # M3: begin_commit reserves the slot + returns a frozen snapshot; ops staged
    # AFTER begin_commit (i.e. during the network POST) must SURVIVE finish_commit.
    s = Session(project="p", buffer_cap=100)
    s.create_element(type="PartDefinition", name="A", owner="root")
    tok = s.review_changes()["confirm_token"]
    snapshot = s.begin_commit(tok)                 # 2 ops snapshotted, guard set
    s.create_element(type="PartDefinition", name="B", owner="root")  # staged during POST
    s.finish_commit(snapshot)                       # clears only the committed 2 ops
    remaining = s.staged_ops()
    assert len(remaining) == 2                       # B's element+membership survive
    assert all(o["payload"]["@type"] != "PartDefinition" or
               o["payload"].get("declaredName") == "B" for o in remaining
               if o["payload"] and o["payload"]["@type"] == "PartDefinition")


def test_begin_commit_rejects_double_commit():
    s = Session(project="p", buffer_cap=100)
    s.create_element(type="PartDefinition", name="A", owner="root")
    tok = s.review_changes()["confirm_token"]
    s.begin_commit(tok)                              # in flight
    tok2 = s.review_changes()["confirm_token"]       # (would need re-review normally)
    with pytest.raises(TokenError, match="already in flight"):
        s.begin_commit(tok2)
