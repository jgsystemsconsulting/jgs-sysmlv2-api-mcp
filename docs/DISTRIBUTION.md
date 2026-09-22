<!--
Copyright (c) 2026 JG Systems Consulting Ltd. All Rights Reserved.
See LICENSE for terms.
-->

# Distribution ledger · jgs-sysmlv2-api-mcp

One row per place this product is, or could be, distributed and discovered
(`RR-B-36`, release-repo-standard). Statuses: `submitted` (URL + date, filed by the
maintainer), `in progress`, `deferred`, `deliberate N/A`, `planned`. A non-submitted
row MUST carry the decision and its date so the question stays closed until its
premises change. Revisit at every release: move statuses, re-date reasons whose
premises changed, never drop a row silently. An agent never marks a row `submitted`;
filing is the maintainer's action and this ledger records it.

Channel precedent: the SysML v1 bridge (`jgs-magic-sysmlv1-mcp`) is listed on Glama
and installs through the in-repo host marketplaces; it was never filed on Smithery,
PulseMCP, or any awesome-list other than an open `awesome-mcp-servers` PR (#14067).
This ledger follows that precedent.

Last reviewed: v2.0.0 / 2026-09-22

## In-host marketplaces (manifests shipped, RR-B-29a)

| Channel | Manifest | Status | Decision / reason | Date |
|---|---|---|---|---|
| Claude Code (in-repo): `/plugin marketplace add jgsystemsconsulting/jgs-sysmlv2-api-mcp` | `.claude-plugin/` | submitted | Primary install path; works from publish day. Official anthropics/claude-plugins-official review not pursued: closed curation, proprietary posture. | 2026-07-05 |
| Cursor (in-repo): point Cursor at this repo | `.cursor-plugin/` | submitted | Manifest + in-repo install. cursor.com marketplace requires an open-source licence; proprietary posture (§0.3), so directory filing is deliberate N/A. | 2026-07-05 |
| OpenAI Codex CLI (in-repo) | `.agents/plugins/` | submitted | Manifest + in-repo install; official Plugin Directory not filed (same licence-bar reasoning as Claude). | 2026-07-05 |
| Gemini CLI (in-repo): `gemini extensions install https://github.com/jgsystemsconsulting/jgs-sysmlv2-api-mcp` | `gemini-extension.json` | submitted | Manifest + verifiable in-repo install; geminicli.com gallery not filed. | 2026-07-05 |

## Web directories & catalogues

| Channel | Artifact | Status | Decision / reason | Date |
|---|---|---|---|---|
| GitHub About + topics + Releases | `scripts/configure_repo.sh` | submitted | Description, homepage (Pages URL), and product topics live; host tags (claude-code, cursor, gemini-cli, openai-codex) plus model-context-protocol and systems-engineering added 2026-09-09 to match the v1 bridge pattern. v2.0.0 published 2026-09-22 with licence-enquiry URL in the notes; exe unsigned pending Trusted Signing enrollment (maintainer override, disclosed in notes). | 2026-09-22 |
| Org catalogue entry | landing page | planned | No org catalogue page exists yet; the Pages landing page (jgsystemsconsulting.github.io/jgs-sysmlv2-api-mcp) is the product entry. Revisit when the org site grows a catalogue. | 2026-09-09 |
| Community awesome-lists (general) | PR or form entry | deferred | Assess each list's licence bar before submitting (§0.3, RR-B-29b gate); proprietary posture blocks most curated lists. | 2026-09-09 |

## MCP aggregator directories (RR-M-07)

| Channel | Artifact | Status | Decision / reason | Date |
|---|---|---|---|---|
| Glama | `glama.json` claim (commit 5f64568) | submitted | Listing live: https://glama.ai/mcp/servers/jgsystemsconsulting/jgs-sysmlv2-api-mcp (shows v1.0.1). Score badge added to README 2026-09-09. | 2026-07-05 |
| awesome-mcp-servers (feeds Glama) | PR entry | in progress | v1-bridge entry PR #14067 merged 2026-09-13. This repo's entry filed as PR #14513 on 2026-09-16 (alphabetically adjacent to the v1 entry, Glama score badge included); awaiting maintainer merge, revisit at next release. | 2026-09-16 |
| Smithery | `smithery.yaml` | deferred | Ships for manual connect; server not listed as of 2026-09-09. v1 precedent: never listed, no user pull observed. Re-file only if a customer asks. | 2026-09-09 |
| PulseMCP | add-server form | deferred | Not listed as of 2026-09-09. v1 precedent: never submitted; auto-crawl has not picked the repo up. Re-check at next release. | 2026-09-09 |
