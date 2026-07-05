# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
import pytest

from jgs_sysmlv2_api_mcp.tools.nav_tools import traverse


def test_cycle_detected_signal():
    # A owns B owns A (cycle): must terminate AND report the cycle (SC10), not just dedupe.
    graph = {"A": ["B"], "B": ["A"]}
    result = traverse(root="A", get_children=lambda n: graph.get(n, []), max_depth=100)
    assert set(result["visited"]) == {"A", "B"}   # each visited once, terminates
    assert result["cycle_detected"] is True       # signal fired
    assert "A" in result["cycle_nodes"]            # the re-encountered node is named


def test_depth_cap_signals():
    graph = {f"n{i}": [f"n{i+1}"] for i in range(10)}
    with pytest.raises(ValueError, match="depth-exceeded"):
        traverse(root="n0", get_children=lambda n: graph.get(n, []), max_depth=3)
