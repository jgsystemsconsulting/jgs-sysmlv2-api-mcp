# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
import anyio

from .server import main

if __name__ == "__main__":
    anyio.run(main)
