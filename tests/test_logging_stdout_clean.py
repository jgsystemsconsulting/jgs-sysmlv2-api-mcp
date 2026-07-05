# Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE.
# SPDX-License-Identifier: LicenseRef-JGSC-Proprietary
import sys, logging, io
from jgs_sysmlv2_api_mcp.logging_setup import configure_logging

def test_logs_go_to_stderr_not_stdout(capsys):
    configure_logging(destination="stderr", secrets=["SEKRIT"])
    logging.getLogger("jgs").warning("token=SEKRIT endpoint=x")
    captured = capsys.readouterr()
    assert captured.out == ""              # stdout MUST be clean (MCP JSON-RPC channel)
    assert "SEKRIT" not in captured.err    # secret redacted
    assert "endpoint=x" in captured.err

def test_secret_redacted_in_exception_and_4xx_sinks(capsys):
    # SC7: the token must be absent from EVERY sink, not just plain log lines —
    # exception messages and 4xx error-body echoes are logged too.
    configure_logging(destination="stderr", secrets=["SEKRIT"])
    log = logging.getLogger("jgs")
    try:
        raise ValueError("auth failed with token=SEKRIT")
    except ValueError:
        log.exception("request failed")          # logs the traceback incl. the message
    log.error("server 400 body: {'error':'bad token SEKRIT'}")  # simulated 4xx echo
    err = capsys.readouterr().err
    assert "SEKRIT" not in err                   # redacted across exception + 4xx sinks
    # commit-metadata sink: the confirm/auth token is never written to commit bodies —
    # asserted structurally in Task 9 (build_commit_body emits no token field).
