<!-- Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE. -->

# jgs-sysmlv2-api-mcp

An MCP server that gives an AI agent read and write access to a live SysML v2 model through the vendor-neutral OMG SysML v2 REST API.

## What it is, who it's for

This server talks to any conformant SysML v2 API endpoint: the OMG reference pilot, or a commercial implementation. There is no CATIA Magic, no desktop tool, no GUI in the loop. If your systems model already lives in a headless SysML v2 API repository, and you want an AI agent to explore it, extend it, or restructure it directly, this is the bridge.

Writes go through a staged-commit model. `create`, `modify`, and `delete` operations accumulate in an in-process buffer, get reviewed as a batch, and are posted as one atomic commit gated by a confirmation token bound to the exact buffer contents. Nothing reaches the API until you have seen what is about to be sent.

It is for teams and individual engineers who want an agent working directly against a SysML v2 API project: exploring an existing model, authoring new elements and relationships, running parallel branches per agent session, or managing project lifecycle, all through the standard API rather than a proprietary desktop integration.

> Companion to `jgs-magic-sysmlv2-mcp`, which drives a running Cameo instance instead. Use this server when the model lives in a headless SysML v2 API repository; use the Cameo bridge when it lives in a running Cameo desktop session.

## Install

```bash
pip install -e .
pip install "git+https://github.com/Systems-Modeling/SysML-v2-API-Python-Client.git"
```

Requires Python 3.11 or later. See `docs/install.md` for prerequisites, the local pilot Docker recipe, and how to verify the install with the `ping` tool.

## Usage

Set the required environment variables and run the server over stdio:

```bash
export SYSMLV2_BASE_URL=https://your-sysmlv2-endpoint.example.com
export SYSMLV2_TOKEN=your-bearer-token
export SYSMLV2_PROJECT=your-project-uuid
python -m jgs_sysmlv2_api_mcp
```

The server exposes 35 tools across five areas: navigation reads, staged authoring writes, project lifecycle, branch and tag versioning, and infrastructure (`ping`, `stats`). See `docs/usage.md` for four fully walked workflows (exploring an unfamiliar model, authoring and committing a change, running one branch per agent session, and managing project lifecycle), and `docs/TOOL-REFERENCE.md` (or the browsable [`docs/index.html`](docs/index.html) / [`docs/tool-reference.html`](docs/tool-reference.html) pages) for the complete, generated tool list with parameters.

### Install with your AI agent

```
Repository: https://github.com/jgsystemsconsulting/jgs-sysmlv2-api-mcp
Version:    v1.0.0

Install:
  pip install -e .
  pip install "git+https://github.com/Systems-Modeling/SysML-v2-API-Python-Client.git"

Human step (cannot be automated): add this server to your MCP client's
config (see examples/mcp.json.example) and restart the client so it
picks up the new server.
```

This repo also ships host-native plugin manifests, so it can be discovered from inside a
coding-agent host rather than hand-edited into an MCP config: Claude Code
(`/plugin marketplace add jgsystemsconsulting/jgs-sysmlv2-api-mcp`), Cursor
(`.cursor-plugin/`, point Cursor at this repo), OpenAI Codex CLI (`.agents/plugins/marketplace.json`,
also read via the legacy `.claude-plugin/` path), and Gemini CLI
(`gemini extensions install https://github.com/jgsystemsconsulting/jgs-sysmlv2-api-mcp`).

## License

Proprietary, copyright 2026 JG Systems Consulting Ltd. See `LICENSE` for full terms and `docs/licensing.md` for a plain-language summary and how to request a license.

## Support

Open an issue on GitHub for bugs and questions. For security vulnerabilities, follow the private reporting process in `SECURITY.md` rather than opening a public issue.

## Design notes

Three ground-truth facts, discovered by a day-one spike against the pilot, shape the code:

1. **The commit POST body is a `CommitRequest`, not a `Commit`.** There is no client-supplied top-level `@id`; the server assigns the commit id.
2. **The official client's typed `Element` model drops `declaredName` and other SysML payload fields.** Reads go through a raw-JSON path instead of typed models.
3. **Reconciliation keys on branch head-advance, not a client-minted commit id.** The commit list is not guaranteed to be newest-first, so head is always resolved by walking `previousCommit` parentage, never by trusting list order.

The full spike results, design decisions, and tier-by-tier implementation history live in `docs/dev/`, which is engineering history, not customer documentation.

## Version

Current release: **v1.0.0**. See `CHANGELOG.md` for what changed.
