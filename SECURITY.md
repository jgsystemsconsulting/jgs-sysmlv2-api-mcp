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

## Signing secrets

Release signing uses two credential families, both env-only and never committed
to this repository:

- Azure Trusted Signing: `TS_ENDPOINT`, `TS_ACCOUNT`, `TS_PROFILE`, and
  `TS_DLIB` (local path to `Azure.CodeSigning.Dlib.dll`). The `/dmdf` metadata
  file is generated at sign time in a temp directory and deleted afterward;
  nothing credential-shaped is ever committed.
- Local certificate: `SIGN_THUMBPRINT` or `SIGN_PFX` (plus
  `SIGN_PFX_PASSWORD`), with optional `SIGN_TIMESTAMP_URL`.

Setting both families at once is rejected as ambiguous by
`scripts/sign_file.ps1`; it fails closed. Partial Trusted Signing credentials
also fail closed with an enrollment pointer (see the release runbook,
`docs/dev/release-runbook.md`, section "Azure Trusted Signing enrollment").

> `-AllowUnsigned` exists for local dev-tree iterations of the gate on an
> unsigned build. Never set it when cutting a release: a `dist/` artifact
> destined for a GitHub Release must pass `verify_release.ps1` with the switch
> omitted.

## General support

Non-security questions: open an issue, or contact
support@jgsystemsconsulting.com. That address is the org's shared,
monitored support inbox (not a personal mailbox); security reports should
still come through the private-advisory route above.
