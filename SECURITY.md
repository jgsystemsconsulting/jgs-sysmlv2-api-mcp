<!-- Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE. -->

# Security Policy

## Reporting a vulnerability

Report security issues privately via a
[GitHub security advisory](https://github.com/jgsystemsconsulting/jgs-sysmlv2-api-mcp/security/advisories/new).
Please do not open a public issue for a suspected vulnerability.

We aim to acknowledge reports within 5 business days. Please include the
affected version (see RELEASE-INFO.txt), reproduction steps, and impact.

## Scope notes

This server holds a bearer token (`SYSMLV2_TOKEN`) in its environment and
enforces an HTTPS-or-loopback rule on the API endpoint. Reports about token
handling, SSRF, or the staged-commit confirmation flow are especially
welcome.

## General support

Non-security questions: open an issue, or contact
support@jgsystemsconsulting.com.
