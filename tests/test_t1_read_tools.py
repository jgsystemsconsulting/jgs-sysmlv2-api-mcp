# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""T1 tests — diff_commits (client-side; pilot 404s the native diff endpoint)."""
from unittest.mock import MagicMock

from jgs_sysmlv2_api_mcp.tools.read_tools import diff_commits


def _api(base_elements, compare_elements):
    api = MagicMock()
    api.get_elements.side_effect = lambda cid: {"base": base_elements,
                                                "comp": compare_elements}[cid]
    return api


def test_diff_buckets_created_deleted_modified():
    base = [{"@id": "keep", "declaredName": "A"},
            {"@id": "gone", "declaredName": "B"},
            {"@id": "edit", "declaredName": "old"}]
    comp = [{"@id": "keep", "declaredName": "A"},
            {"@id": "new", "declaredName": "C"},
            {"@id": "edit", "declaredName": "NEW"}]
    got = diff_commits(_api(base, comp), "base", "comp")
    assert got == {"created": ["new"], "deleted": ["gone"], "modified": ["edit"]}


def test_diff_identical_commits_is_empty():
    els = [{"@id": "x", "declaredName": "A"}]
    got = diff_commits(_api(els, list(els)), "base", "comp")
    assert got == {"created": [], "deleted": [], "modified": []}
