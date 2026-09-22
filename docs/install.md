<!-- Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE. -->

# Install

`jgs-sysmlv2-api-mcp` ships as a Windows executable. There is no Python to
install: download the exe from the Releases page, verify it against the
published checksums, place your licence file (PRO tiers only; the FREE read
tools need no licence), set three environment variables, and point your MCP
client at the exe.

## Prerequisites

- Windows 10 or later.
- An MCP client that can launch a local server over stdio (Claude Code, Claude Desktop, or any other MCP-compatible client).
- A SysML v2 API endpoint: either a commercial implementation or a local instance of the OMG pilot (see below).

## Download and verify

Download `jgs-sysmlv2-api-mcp.exe` and `SHA256SUMS.txt` from the
[Releases page](https://github.com/jgsystemsconsulting/jgs-sysmlv2-api-mcp/releases)
into the same folder.

Verify the exe against the checksum file before running it (PowerShell):

```powershell
$line = Select-String -Path .\SHA256SUMS.txt -Pattern "jgs-sysmlv2-api-mcp.exe"
$hash = (Get-FileHash .\jgs-sysmlv2-api-mcp.exe -Algorithm SHA256).Hash.ToLower()
$line.Line.StartsWith($hash)   # must print True
```

A `False` result, or a missing line, means the file does not match the
published checksum: do not run it. Both files come from the same release, so
if the check fails, re-download both from that release page.

## Place the licence (PRO tiers)

The FREE tier needs no licence file: all read and navigation tools work out
of the box. The PRO authoring tools (and ENTERPRISE/ACADEMIC, functionally
identical) unlock when the server finds a valid licence file named
`jgsc-sysmlv2-api-pro.licence`.

With the executable, the entry-point directory is the directory containing
the exe, so the simplest placement is to put the licence file in the same
folder as `jgs-sysmlv2-api-mcp.exe`. Alternatively, set the
`JGS_V2_API_LICENCE_PATH` environment variable to the full path of the file.

At startup the server looks for the licence in this order, and the first
existing file wins:

1. The path in `JGS_V2_API_LICENCE_PATH`, if set.
2. The directory containing the exe.
3. `~/.jgs-sysmlv2-api/`.

A stale or invalid file at a higher-precedence location shadows a valid one
lower down: the search does not fall through past the first file it finds.
Use the `get_licence` tool from your client to see which file actually
loaded. Licence changes take effect on restart: because MCP clients own the
server process, installing or renewing a licence requires restarting your
MCP client (or its server entry) before the new tier applies.

## Set the environment variables

| Variable | Required | Meaning |
|---|---|---|
| `SYSMLV2_BASE_URL` | yes | SysML v2 API endpoint, for example `http://localhost:9000` for a local pilot. |
| `SYSMLV2_TOKEN` | yes | Bearer token sent on every request. |
| `SYSMLV2_PROJECT` | yes | Project UUID the server binds to. |

Set them in the `env` block of your MCP client config (next section) so the
exe inherits them on every launch. On an open local pilot that does not
validate the bearer token, any non-empty placeholder works for
`SYSMLV2_TOKEN`; the server requires a non-empty value. Full reference,
including the optional `SYSMLV2_BRANCH` and the HTTPS/loopback rule:
`docs/configuration.md`.

## Point your MCP client at the exe

Copy `examples/.mcp.json.example` from the repository (or the block below)
into your client's config location, drop the `.example` suffix, fill in the
placeholders, and restart the client:

```json
{
  "mcpServers": {
    "jgs-sysmlv2": {
      "command": "C:\\path\\to\\jgs-sysmlv2-api-mcp.exe",
      "env": {
        "SYSMLV2_BASE_URL": "https://your-sysmlv2-endpoint.example.com",
        "SYSMLV2_TOKEN": "YOUR_BEARER_TOKEN_HERE",
        "SYSMLV2_PROJECT": "YOUR_PROJECT_UUID_HERE"
      }
    }
  }
}
```

`command` is the full path to the exe. If you added the exe's folder to your
PATH, the bare filename `jgs-sysmlv2-api-mcp.exe` also works. The host-native
plugin manifests (Claude Code, Cursor, OpenAI Codex CLI) are discovery
metadata only; the manifests that expose a launch command
(gemini-extension.json, smithery.yaml) already point at the exe, and the same
absolute-path rule applies if you copy their shape.

## Running a local SysML v2 API pilot

If you do not have access to a commercial SysML v2 API endpoint, the OMG reference pilot is a good way to try the server locally. The pilot itself is a Scala/Play application that normally requires a JDK and sbt to build from source. The fastest path is the prebuilt Docker image backed by PostgreSQL:

The image used below, `mbsemashup/sysmlv2-api.pilotimpl`, is a third-party containerization of the official pilot source (built from the MBSE-mashup fork of Systems-Modeling/SysML-v2-API-Services), not an image published by the Systems-Modeling project itself. It tracks the pilot loosely rather than release-for-release. For a reproducible setup, pin the image by digest instead of `latest`, and expect the newest pilot release features to arrive late.

```bash
docker network create sysml-net

docker run -d --name sysml2-postgres --network sysml-net \
  -e POSTGRES_PASSWORD=mysecretpassword -e POSTGRES_DB=sysml2 -p 5432:5432 postgres:16

docker run -d --name sysml2-pilot --network sysml-net -p 9000:9000 \
  -e JDBC_DRIVER="org.postgresql.Driver" \
  -e JDBC_URL="jdbc:postgresql://sysml2-postgres:5432/sysml2" \
  -e JDBC_USER="postgres" -e JDBC_PASSWORD="mysecretpassword" \
  -e HIBERNATE_DIALECT="org.hibernate.dialect.PostgreSQLDialect" \
  -e HIBERNATE_HBM2DDL="create" \
  mbsemashup/sysmlv2-api.pilotimpl:latest
```

The first boot builds the full metamodel schema, which takes one to two minutes. Once it is up, confirm the pilot answers:

```bash
curl http://localhost:9000/projects
# -> 200 []
```

If the container was previously stopped uncleanly, the pilot process can come up wedged behind a stale PID file. If `docker start sysml2-pilot` does not bring the API back, remove and recreate the container instead of restarting it:

```bash
docker rm -f sysml2-pilot
docker run -d --name sysml2-pilot --network sysml-net -p 9000:9000 \
  -e JDBC_DRIVER="org.postgresql.Driver" \
  -e JDBC_URL="jdbc:postgresql://sysml2-postgres:5432/sysml2" \
  -e JDBC_USER="postgres" -e JDBC_PASSWORD="mysecretpassword" \
  -e HIBERNATE_DIALECT="org.hibernate.dialect.PostgreSQLDialect" \
  -e HIBERNATE_HBM2DDL="create" \
  mbsemashup/sysmlv2-api.pilotimpl:latest
```

## Create your first project

A fresh pilot answers `curl http://localhost:9000/projects` with `[]`: it has no projects yet. The server requires `SYSMLV2_PROJECT` at startup and routes every tool call through that project, so the variable needs to name a project that exists. Create one now, directly against the pilot:

```bash
curl -s -X POST http://localhost:9000/projects \
  -H "Content-Type: application/json" \
  -d '{"@type": "Project", "name": "sandbox"}'
```

The response is the new project record. Copy its `@id` value and use it as `SYSMLV2_PROJECT` in your client config. (The `create_project` MCP tool does the same thing, but it needs a PRO licence; the curl route works on every tier, including the free one.)

If your endpoint is not a fresh pilot and already carries projects, list them with `curl http://localhost:9000/projects` (or with `list_projects` after connecting) and pick an existing `@id` instead of creating one.

## Verify the install

The server speaks the MCP stdio protocol, so it prints nothing on a bare
launch; it waits for an MCP client to connect. Restart your MCP client so it
picks up the config, then ask your agent to call `ping`, the smallest tool in
the registry: it does a live round trip to the configured project's commit
list and reports whether the connection is healthy.

A working response looks like:

```json
{"up": true, "api_version": null, "commit_count": 0}
```

If `SYSMLV2_PROJECT` does not match a real project on the endpoint, `ping`
still reports `"up": true` but adds a `warning` naming the missing project;
fix the variable (or create the project as shown above) before going further.
If `ping` fails outright, recheck `SYSMLV2_BASE_URL` and `SYSMLV2_TOKEN`
before anything else: nearly every install problem traces back to one of
those two.

## Next steps

- `docs/configuration.md` for the full environment variable reference.
- `docs/usage.md` for walked examples of the core workflows.
- `docs/TOOL-REFERENCE.md` for the complete tool list.
