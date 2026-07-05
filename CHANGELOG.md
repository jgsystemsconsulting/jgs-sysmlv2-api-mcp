<!-- Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE. -->

# Changelog

All notable changes to jgs-sysmlv2-api-mcp are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project uses [Semantic Versioning](https://semver.org/).

## [1.0.1] - 2026-07-05

### Added
- Host-native plugin manifests for Cursor (`.cursor-plugin/`), OpenAI Codex CLI
  (`.agents/plugins/marketplace.json`), and Gemini CLI (`gemini-extension.json`),
  alongside the existing Claude Code manifest, so the server is discoverable and
  installable from all four mainstream coding-agent hosts.

### Changed
- The release payload no longer ships the `tests/` directory or the
  `pytest`/`nuitka` dev dependencies; customers install via `pip` and don't run
  the internal test suite. CI in the release repo now installs runtime deps and
  runs only the release gate.

## [1.0.0] - 2026-07-03

First full release: the complete 35-tool v1 surface.

### Added
- Navigation reads: project, roots, children, relationships, name lookup,
  commits, commit changes, client-side diff (T1).
- Versioning lifecycle: branches, tags, session branch retargeting, and a
  conflict-refusing client-side squash merge (T2).
- Project lifecycle: create, update (echo-PUT), and verified delete with a
  configured-project guard (T3).
- Authoring extensions: typed relationship staging with end-field mapping,
  element rehoming, and atomic batch staging (T4).
- Staged-commit write model with fingerprint-bound confirmation tokens,
  ambiguous-write reconciliation, and SSRF-hardened transport (v0).

### Notes
- Verified against the OMG SysML v2 pilot implementation; pilot deviations
  from the published OpenAPI are documented in docs/dev/tool-catalog.md and
  pinned by the integration test suite.
