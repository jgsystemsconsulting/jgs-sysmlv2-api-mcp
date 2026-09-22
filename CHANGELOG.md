<!-- Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE. -->

# Changelog

All notable changes to jgs-sysmlv2-api-mcp are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project uses [Semantic Versioning](https://semver.org/).

## [2.0.0] - 2026-09-22

The V2.0 milestone cut: the distribution model inverts to docs+binary. The
public repository becomes a documentation-and-download site, and the product
ships as a native-compiled, Authenticode-signed Windows executable published
as a GitHub Release asset with a `SHA256SUMS.txt` checksum file. The 39-tool
surface, the FREE/PRO licence tiers, and the staged-commit authoring model
are unchanged from 1.0.x.

### Added
- Windows binary distribution: `jgs-sysmlv2-api-mcp.exe` (Nuitka onefile,
  no extractable bytecode) with licence-gate enforcement compiled in, plus
  `SHA256SUMS.txt`, attached to the v2.0.0 GitHub Release.
- `docs/install.md` is now the binary-install guide (download, checksum
  verify, licence placement, environment variables, MCP client wiring);
  source-checkout instructions for contributors live in the development
  repository.

### Fixed
- `delete_subtree` now also drops staged creates inside the doomed subtree
  (and refuses to re-home staged modifies), so a failed staging cascade no
  longer leaves orphaned buffer entries; ownership is resolved against a
  per-head-commit element snapshot instead of assuming names are stable
  across branch switches.
- A commit that hits a timeout after the server accepted the write no longer
  dead-ends in an "ambiguous write" error: the server reconciles first, and a
  write that landed is reported as committed with the resulting commit id.
- `query_elements` pagination is now deterministic: stable element ordering,
  an opaque cursor that survives page-size changes, and `page_size` is
  honored on every page including the first.
- Missing-token startup guidance is accurate: the error names the MCP
  client's `env` block as the delivery mechanism, `smithery.yaml` marks
  `SYSMLV2_TOKEN` as required, and a locally filled-in `.mcp.json` is
  gitignored so a real bearer token cannot be committed by accident.
- The v1-to-v2 migration guide no longer links to a private planning path;
  the full kept-name rationale from the v2 naming audit now ships with the
  repository.

### Changed
- Development packaging: the SysML v2 API client dependency is pinned to
  upstream commit `8971105f` (tag 2021-09), so development installs are
  reproducible instead of tracking the upstream default branch.
- Development packaging: the project declares a minimal PEP 517 build-system
  table, ending pip's implicit build fallback in the development tree.
- Development automation: the validate workflow no longer installs the SysML
  v2 API client a second time alongside its declared install, so the
  development tree has one declared install path.

## [1.0.2] - 2026-09-09

### Added
- `docs/install.md`: first-project bootstrap section. A fresh pilot has no
  projects while `SYSMLV2_PROJECT` is required at startup, so the install now
  walks through creating the first project with `curl` and setting the
  variable to its `@id` before the `ping` verify step.

### Changed
- The official SysML v2 API Python client is now declared in `pyproject.toml`
  as a direct git dependency; `pip install -e .` alone is a complete install
  (previously a second manual `pip install` from git was required, and
  skipping it produced a bare ImportError traceback at startup).
- `ping` distinguishes "endpoint down" from "configured project not found":
  when the project-scoped probe fails but the endpoint answers, it reports
  `"up": true` with a `warning` naming the missing project instead of failing.
- `docs/install.md` discloses that the local pilot Docker image
  (`mbsemashup/sysmlv2-api.pilotimpl`) is a third-party containerization of
  the official pilot source, and recommends pinning it by digest.
- `docs/TOOL-REFERENCE.md` and `docs/tool-reference.html` regenerated from the
  live registry; the `export_project` and `validate_model` descriptions had
  drifted from the tool descriptions the server actually registers.
- Landing page (`docs/index.html`): install section matches the single-command
  install, and the example MCP config filename is corrected to
  `examples/.mcp.json.example`.

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
