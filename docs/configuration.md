<!-- Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE. -->

# Configuration

The server is configured entirely through environment variables. There is no config file, and the bearer token must never be written into a committed file, including your MCP client's own config.

## Environment variables

| Variable | Required | Default | Meaning |
|---|---|---|---|
| `SYSMLV2_BASE_URL` | yes | none | The SysML v2 API endpoint, for example `https://sysmlv2.example.com` or `http://localhost:9000` for a local pilot. |
| `SYSMLV2_TOKEN` | yes | none | Bearer token sent as `Authorization: Bearer <token>` on every request. |
| `SYSMLV2_PROJECT` | yes | none | UUID of the project the write buffer is bound to. Reads default to this project unless a tool call overrides `project_id`. |
| `SYSMLV2_BRANCH` | no | the project's default branch | Branch id (not a branch name) the session starts on. See "Branch pinning" below. |

Two more variables tune behavior but are not required:

| Variable | Default | Meaning |
|---|---|---|
| `SYSMLV2_PAGE_SIZE` | `50` | Default page size for `query_elements` when the tool call does not specify one. |

Two further limits are fixed in code rather than read from the environment, but are worth knowing:

- **Buffer cap**: 5000 staged operations. `create_element`, `modify_element`, `delete_element`, `delete_subtree`, `create_relationship`, `move_element`, and `stage_batch` all accumulate in one in-process buffer per session; once it holds 5000 operations, further staging is refused until you `commit_changes` or `discard_changes`.
- **Confirm-token TTL**: 120 seconds. `review_changes` returns a confirm token bound to a fingerprint of the current buffer. `commit_changes` rejects a token older than 120 seconds or one that no longer matches the buffer it was issued for, so a stale or reused token cannot silently commit changes you never reviewed.

## The HTTPS/loopback rule

`SYSMLV2_BASE_URL` is validated before any network call is made:

- `https://` is accepted for any host.
- `http://` is accepted **only** if every IP address the host resolves to is loopback (`127.0.0.0/8` or `::1`).

This closes the obvious ways to point the server at an internal service over plaintext: a DNS name that resolves to a non-loopback address, a decimal or hex-encoded IP literal, or a link-local address are all rejected. In practice this means `http://localhost:9000` and `http://127.0.0.1:9000` work for local development, and anything reaching outside your machine must use `https://`.

## `examples/.mcp.json.example`

The repository ships an example MCP client configuration at `examples/.mcp.json.example`:

```json
{
  "mcpServers": {
    "jgs-sysmlv2": {
      "command": "python",
      "args": ["-m", "jgs_sysmlv2_api_mcp"],
      "env": {
        "SYSMLV2_BASE_URL": "https://your-sysmlv2-endpoint.example.com",
        "SYSMLV2_TOKEN": "YOUR_BEARER_TOKEN_HERE",
        "SYSMLV2_PROJECT": "YOUR_PROJECT_UUID_HERE"
      }
    }
  }
}
```

To use it: copy the file to wherever your MCP client reads server configs from (for example `.mcp.json` in a project root, or your client's global config location), rename it by dropping the `.example` suffix, and fill in the three placeholder values. Add `SYSMLV2_BRANCH` to the `env` block if you want the session to start on a specific branch rather than the project's default.

Do not commit the filled-in file. Keep the token out of version control entirely; treat `examples/.mcp.json.example` as the template and your real config as local, untracked state.

## Branch pinning: `SYSMLV2_BRANCH` vs. `set_branch`

There are two ways to control which branch a session works against, and they serve different purposes:

- **`SYSMLV2_BRANCH`** sets the branch a session starts on at server boot. It is a fixed environment variable, so it is the right choice when you always want this server instance to work against the same branch, for example a per-agent branch in a branch-per-agent-session workflow.
- **`set_branch`** retargets an already-running session to a different branch id at any time. It is refused while staged (uncommitted) work exists, so you cannot switch branches out from under a pending commit. Use it when a session needs to move between branches during a conversation, for example to check a colleague's work before returning to your own.

If neither is set, the session resolves the project's default branch automatically and stays there.
