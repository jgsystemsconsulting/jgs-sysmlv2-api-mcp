<!-- Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE. -->

# Licensing

`jgs-sysmlv2-api-mcp` ships as **`sysmlv2-api-pro`**: a compiled Windows binary
whose authoring capability is unlocked by a licence file. This page covers the
product licence. It does not change the source code's own terms (below).

## Source code vs. product licence — two different things

- **The source code** in this repository is proprietary and confidential,
  copyright JG Systems Consulting Ltd. No license, express or implied, is
  granted to use, copy, modify, merge, publish, distribute, sublicense, or
  sell it, in whole or in part, without prior written permission. See
  `LICENSE` at the repository root for the full terms.
- **The compiled binary's write tools** are gated separately by a product
  licence tier, described below. Buying or trialling a PRO licence does not
  grant any right to the source code; it only unlocks authoring tools in the
  binary you were given.

## Tiers

- **FREE** — no licence file needed. All read/navigation tools work
  out of the box: browsing a model, querying elements, listing commits,
  branches, and tags, and so on.
- **PRO** (also **ENTERPRISE** and **ACADEMIC**, functionally identical to PRO
  at launch — only pricing/terms differ) — unlocks the 15 gated authoring
  tools: `create_element`, `modify_element`, `delete_element`,
  `delete_subtree`, `create_relationship`, `move_element`, `stage_batch`,
  `commit_changes`, `create_branch`, `delete_branch`, `merge_branch`,
  `create_tag`, `create_project`, `update_project`, `delete_project`.

Gated tools always appear in the tool list; only invocation is denied without
a valid PRO-or-above licence.

## How enforcement works

- Licences are Ed25519-signed, fully offline. There is no machine binding and
  no phone-home; the server never contacts a license server.
- The licence file is named **`jgsc-sysmlv2-api-pro.licence`**. At startup the
  server looks for it in this order, and **the first existing file wins**:
  1. The path in the `JGS_V2_API_LICENCE_PATH` environment variable, if set.
  2. The directory containing the deployed executable.
  3. `~/.jgs-sysmlv2-api/`.

  A stale or invalid file at a higher-precedence location **shadows** a valid
  one lower down — the search does not fall through past the first file it
  finds, it selects that file and reports whatever reason it failed
  verification for. Use the `get_licence` tool (below) to see which file
  actually loaded.
- **Licence changes only take effect on server respawn.** Because MCP clients
  own the server process, installing or renewing a licence requires
  restarting your MCP client (or its server entry) before the new tier
  applies. This is true every time, not just on first install.
- Missing, invalid, tampered, or expired licences degrade the server to FREE
  mode. It never crashes and never hard-stops.

## Checking your licence

Call the **`get_licence`** MCP tool from within your client to see the current
tier, validity, expiry date, and which file (if any) was loaded.

## The `.licence` file is a bearer credential

Anyone holding a copy of your `.licence` file has the entitlement it grants.
Treat it like a secret: do not commit it, publish it, or share it outside
your organization.

## Trial licences

Email **support@jgsystemsconsulting.com** for a short-expiry PRO trial
licence.

## Pricing

Pricing for `sysmlv2-api-pro` has not yet been set. Contact
**support@jgsystemsconsulting.com** for current terms.

## Third-party components

This project depends on the official SysML v2 API Python client and other
open-source packages listed in `pyproject.toml`. Those dependencies retain
their own licenses; using this software does not change the license terms of
its dependencies.
