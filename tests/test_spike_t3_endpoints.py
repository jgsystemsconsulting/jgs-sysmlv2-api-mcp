# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
"""T3 spike tests — pin the pilot HTTP contract (RESULT: PASS 2026-07-02).

Ground truths encoded (docs/dev/tool-catalog.md "Pilot spike results" 17-19):
project create round-trips description; PUT accepts ONLY a full readback
echo (minimal bodies 500 with no effect); DELETE project is a lying-500
(500 but effective). urllib on purpose — pins the HTTP contract independent
of our ApiClient. Requires a live pilot:
  SYSMLV2_HOST=http://localhost:9000 pytest tests/test_spike_t3_endpoints.py -v -m integration
"""
import json
import os
import urllib.error
import urllib.request
import uuid

import pytest

HOST = os.environ.get("SYSMLV2_HOST", "http://localhost:9000")


def _req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(HOST + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as e:
        return e.code, None


@pytest.fixture()
def proj():
    status, p = _req("POST", "/projects",
                     {"@type": "Project", "name": f"t3spike-{uuid.uuid4().hex[:8]}",
                      "description": "d0"})
    assert status == 200
    return p


@pytest.mark.integration
def test_create_project_roundtrips_description(proj):
    assert proj["description"] == "d0"                       # ground truth 17
    status, back = _req("GET", f"/projects/{proj['@id']}")
    assert status == 200 and back["description"] == "d0"


@pytest.mark.integration
def test_put_rejects_minimal_body_accepts_full_echo(proj):
    pid = proj["@id"]
    # minimal bodies: 500 and NO effect (ground truth 18)
    status, _ = _req("PUT", f"/projects/{pid}", {"@type": "Project", "name": "nope"})
    assert status == 500
    status, _ = _req("PUT", f"/projects/{pid}",
                     {"@id": pid, "@type": "Project", "name": "nope", "description": "nope"})
    assert status == 500
    _, unchanged = _req("GET", f"/projects/{pid}")
    assert unchanged["name"] == proj["name"] and unchanged["description"] == "d0"
    # full readback echo with edits: 200 and the update lands
    _, echo = _req("GET", f"/projects/{pid}")
    echo["name"], echo["description"] = "renamed", "d1"
    status, _ = _req("PUT", f"/projects/{pid}", echo)
    assert status == 200
    _, after = _req("GET", f"/projects/{pid}")
    assert after["name"] == "renamed" and after["description"] == "d1"
    assert after["defaultBranch"]["@id"] == proj["defaultBranch"]["@id"]   # untouched


@pytest.mark.integration
def test_delete_project_lying_500_but_effective(proj):
    pid = proj["@id"]
    status, _ = _req("DELETE", f"/projects/{pid}")
    assert status == 500                                     # ground truth 19
    status, _ = _req("GET", f"/projects/{pid}")
    assert status == 404                                     # ...but it worked
    _, projects = _req("GET", "/projects")
    assert all(p["@id"] != pid for p in projects)
