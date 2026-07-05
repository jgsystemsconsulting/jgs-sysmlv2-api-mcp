# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""T4 tests — move_element (D11) and related_ids traversal helper."""
from unittest.mock import MagicMock

import pytest

from jgs_sysmlv2_api_mcp.tools.author_tools import move_element
from jgs_sysmlv2_api_mcp.tools.nav_tools import related_ids


def _api_with_elements(elements):
    api = MagicMock()
    api.get_elements.return_value = elements
    return api


MEMBERSHIP = {"@id": "m1", "@type": "OwningMembership",
              "owningRelatedElement": {"@id": "oldOwner"},
              "ownedMemberElement": {"@id": "child"}}


def test_move_element_stages_membership_rehome():
    api = _api_with_elements([MEMBERSHIP, {"@id": "child", "@type": "PartDefinition"}])
    session = MagicMock()
    got = move_element(api, session, "child", "newOwner", "c1")
    session.modify_element.assert_called_once_with("m1", {
        "@type": "OwningMembership",
        "owningRelatedElement": {"@id": "newOwner"},
        "ownedMemberElement": {"@id": "child"}})
    assert got == {"membership": "m1", "old_owner": "oldOwner", "new_owner": "newOwner"}


def test_move_element_refuses_when_no_membership_found():
    api = _api_with_elements([{"@id": "child", "@type": "PartDefinition"}])
    session = MagicMock()
    with pytest.raises(ValueError, match="found 0"):
        move_element(api, session, "child", "newOwner", "c1")
    session.modify_element.assert_not_called()               # D11


def test_move_element_refuses_when_multiple_memberships_found():
    twin = dict(MEMBERSHIP, **{"@id": "m2"})
    api = _api_with_elements([MEMBERSHIP, twin])
    with pytest.raises(ValueError, match="found 2"):
        move_element(api, MagicMock(), "child", "newOwner", "c1")


def test_related_ids_collects_outgoing_targets():
    api = MagicMock()
    api.get_relationships.return_value = [
        {"@id": "r1", "target": [{"@id": "general1"}]},
        {"@id": "r2", "target": [{"@id": "general2"}, {"@id": "general3"}]},
        {"@id": "r3", "target": []},
    ]
    assert related_ids(api, "c1", "e1") == ["general1", "general2", "general3"]
    api.get_relationships.assert_called_once_with("c1", "e1", direction="out")
