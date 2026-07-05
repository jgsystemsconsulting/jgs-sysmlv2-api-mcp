# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""T1 tests — containment discovery + name lookup.

The pilot does NOT derive ownedMember (spike ground truth #6): child
discovery must scan OwningMembership elements (owningRelatedElement ->
ownedMemberElement, the exact fields Session.create_element writes). A
conformant server that DOES derive ownedMember takes the fast route."""
from unittest.mock import MagicMock

from jgs_sysmlv2_api_mcp.tools.nav_tools import child_ids, get_children


def test_child_ids_fast_route_uses_derived_ownedMember():
    api = MagicMock()
    api.get_element.return_value = {"@id": "root",
                                    "ownedMember": [{"@id": "a"}, {"@id": "b"}]}
    assert child_ids(api, "c1", "root") == ["a", "b"]
    api.get_elements.assert_not_called()          # no scan when derived data exists


def test_child_ids_fallback_scans_memberships():
    api = MagicMock()
    api.get_element.return_value = {"@id": "root", "ownedMember": []}   # pilot shape
    api.get_elements.return_value = [
        {"@id": "root", "@type": "PartDefinition"},
        {"@id": "m1", "@type": "OwningMembership",
         "owningRelatedElement": {"@id": "root"}, "ownedMemberElement": {"@id": "a"}},
        {"@id": "m2", "@type": "OwningMembership",
         "owningRelatedElement": {"@id": "other"}, "ownedMemberElement": {"@id": "b"}},
    ]
    assert child_ids(api, "c1", "root") == ["a"]


def test_get_children_returns_id_name_type():
    api = MagicMock()
    elements = {
        "root": {"@id": "root", "ownedMember": [{"@id": "a"}]},
        "a": {"@id": "a", "@type": "PartDefinition", "declaredName": "Wheel"},
    }
    api.get_element.side_effect = lambda cid, eid: elements[eid]
    assert get_children(api, "c1", "root") == [
        {"id": "a", "name": "Wheel", "type": "PartDefinition"}]


def test_filter_root_ids_excludes_owned_elements():
    """Ground truth 2 (re-verified): the pilot's /roots does NOT filter
    server-side — it returns every element. filter_root_ids removes any
    element that appears as an ownedMemberElement of an OwningMembership
    in the same commit (same scan child_ids' fallback route uses)."""
    from jgs_sysmlv2_api_mcp.tools.nav_tools import filter_root_ids
    api = MagicMock()
    api.get_elements.return_value = [
        {"@id": "root", "@type": "PartDefinition"},
        {"@id": "a", "@type": "PartDefinition"},
        {"@id": "m1", "@type": "OwningMembership",
         "owningRelatedElement": {"@id": "root"}, "ownedMemberElement": {"@id": "a"}},
    ]
    candidates = [{"@id": "root"}, {"@id": "a"}]
    assert filter_root_ids(api, "c1", candidates) == ["root"]


def test_find_by_name_filters_client_side():
    from jgs_sysmlv2_api_mcp.tools.nav_tools import find_by_name
    api = MagicMock()
    # server may ignore the where clause and return everything — the
    # client-side filter must still produce only exact name matches
    api.query.return_value = [
        {"@id": "v", "@type": "PartDefinition", "declaredName": "Vehicle"},
        {"@id": "c", "@type": "PartDefinition", "declaredName": "Car"},
    ]
    got = find_by_name(api, "c1", "Vehicle")
    assert got == [{"id": "v", "name": "Vehicle", "type": "PartDefinition"}]


def test_find_by_name_optional_type_filter():
    from jgs_sysmlv2_api_mcp.tools.nav_tools import find_by_name
    api = MagicMock()
    api.query.return_value = [
        {"@id": "p", "@type": "PartDefinition", "declaredName": "Engine"},
        {"@id": "r", "@type": "RequirementDefinition", "declaredName": "Engine"},
    ]
    got = find_by_name(api, "c1", "Engine", type="RequirementDefinition")
    assert [g["id"] for g in got] == ["r"]
