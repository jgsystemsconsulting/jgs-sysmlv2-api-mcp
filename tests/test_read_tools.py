# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""Task 10 tests — read tools with opaque-cursor pagination contract."""
from unittest.mock import MagicMock

from jgs_sysmlv2_api_mcp.tools.read_tools import query_elements_page


def test_query_returns_page_and_next_cursor():
    ac = MagicMock()
    ac.query.return_value = [{"@id": "1"}, {"@id": "2"}]
    out = query_elements_page(ac, commit_id="c", filter={"name": "Vehicle"},
                               cursor=None, page_size=2)
    assert len(out["elements"]) == 2
    assert "next_cursor" in out
