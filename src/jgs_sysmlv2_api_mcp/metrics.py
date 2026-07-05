# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
from collections import defaultdict

_KEYS = ("commits_attempted", "commits_succeeded", "commits_failed",
         "retries_total", "timeouts_total", "buffer_cap_hits")

class Metrics:
    def __init__(self):
        # Plain dict incr: `+= 1` on a dict value is atomic under the CPython GIL,
        # and snapshot() only reads — no lock needed on the stats/liveness path.
        self._values = defaultdict(int)

    def incr(self, key: str):
        self._values[key] += 1

    def snapshot(self) -> dict:
        return {k: self._values[k] for k in _KEYS}
