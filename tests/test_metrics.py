# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
from jgs_sysmlv2_api_mcp.metrics import Metrics

def test_counters_increment_and_snapshot():
    m = Metrics()
    m.incr("commits_attempted")
    m.incr("commits_succeeded")
    m.incr("commits_attempted")
    snap = m.snapshot()
    assert snap["commits_attempted"] == 2
    assert snap["commits_succeeded"] == 1
    assert snap["buffer_cap_hits"] == 0   # unknown keys default 0
