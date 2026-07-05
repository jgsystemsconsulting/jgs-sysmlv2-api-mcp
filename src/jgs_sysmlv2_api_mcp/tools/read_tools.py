# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""Task 10 — read tools with the single opaque-cursor pagination contract.

Implements spec Section 4 read tools. Pagination is client-side over the
raw query result list: the committed ApiClient.query(commit_id, body) (see
api_client.py, Task 5) takes exactly those two positional args and returns
the full raw-JSON result list for a query — it does NOT accept request-side
paging kwargs (no page_after/page_size parameters, no **kwargs). `cursor`
and `page_size` are accepted here for the tool's external contract (opaque
`next_cursor` handed back to the caller) and are reserved for wiring to
server-side paging once the pilot's paging headers are confirmed live
(Task 14). Until then they are applied client-side after the call rather
than forwarded to api_client.query, so this stays safe against the real
ApiClient (calling it with unsupported kwargs would raise TypeError).
"""


def query_elements_page(api_client, commit_id, filter, cursor=None, page_size=50):
    body = {"@type": "Query", "select": [], "where": filter or {}}
    results = api_client.query(commit_id, body)
    items = [r.to_dict() if hasattr(r, "to_dict") else r for r in results]
    page = items[:page_size]
    next_cursor = page[-1]["@id"] if len(items) >= page_size and page else None
    return {"elements": page, "next_cursor": next_cursor}


def diff_commits(api_client, base_commit, compare_commit):
    """Client-side element-set diff. The spec's native GET .../diff endpoint
    404s on the pilot (T1 plan ground truth 7); swap to it against
    a conformant server. Returns id lists, not payloads (payloads are large;
    callers fetch what they need via get_element).
    ponytail: O(n) full-set diff, fine at pilot scale; walk the commit-chain
    /changes instead if models outgrow it."""
    base = {e["@id"]: e for e in api_client.get_elements(base_commit)}
    comp = {e["@id"]: e for e in api_client.get_elements(compare_commit)}
    return {
        "created": sorted(i for i in comp if i not in base),
        "deleted": sorted(i for i in base if i not in comp),
        "modified": sorted(i for i in comp if i in base and comp[i] != base[i]),
    }
