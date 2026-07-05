# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
import logging
import sys

from .transport import redact


class _RedactingFormatter(logging.Formatter):
    def __init__(self, secrets):
        super().__init__("%(levelname)s %(name)s %(message)s")
        self._secrets = secrets

    def format(self, record):
        msg = super().format(record)
        return redact(msg, self._secrets)


def configure_logging(destination="stderr", secrets=None, log_file=None):
    secrets = secrets or []
    if destination == "file":
        if not log_file:
            raise ValueError("log_file required when destination='file'")
        handler = logging.FileHandler(log_file)     # fail-fast if unwritable
    else:
        handler = logging.StreamHandler(sys.stderr)  # NEVER sys.stdout (fd 1 = MCP channel)
    assert handler.stream is not sys.stdout, "log sink must never be stdout"
    handler.setFormatter(_RedactingFormatter(secrets))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    # Named library loggers: rely on propagation to the root handler above; do NOT
    # add the handler again (that would double every line). Just ensure they are not
    # silenced and let their records bubble to root's single stderr/file handler.
    for noisy in ("urllib3", "sysml_v2_api_client"):
        logging.getLogger(noisy).propagate = True
