<!-- Copyright (c) 2026 JG Systems Consulting Ltd. See LICENSE. -->

# Install

## Prerequisites

- Python 3.11 or later.
- An MCP client that can launch a local server over stdio (Claude Code, Claude Desktop, or any other MCP-compatible client).
- A SysML v2 API endpoint: either a commercial implementation or a local instance of the OMG pilot (see below).

## Install the package

```bash
pip install -e .
```

The server also needs the official SysML v2 API Python client, which is not published to PyPI. Install it directly from its GitHub source:

```bash
pip install "git+https://github.com/Systems-Modeling/SysML-v2-API-Python-Client.git"
```

Both commands can be run in either order; there is no import-time dependency between them.

## Running a local SysML v2 API pilot

If you do not have access to a commercial SysML v2 API endpoint, the OMG reference pilot is a good way to try the server locally. The pilot itself is a Scala/Play application that normally requires a JDK and sbt to build from source. The fastest path is the prebuilt Docker image backed by PostgreSQL:

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

## Verify the install

Set the three required environment variables (see `docs/configuration.md` for details) and start the server over stdio:

```bash
export SYSMLV2_BASE_URL=http://localhost:9000
export SYSMLV2_TOKEN=dev-placeholder
export SYSMLV2_PROJECT=your-project-uuid
python -m jgs_sysmlv2_api_mcp
```

The server speaks the MCP stdio protocol, so it will not print anything on a bare launch; it waits for an MCP client to connect. To check that the server can actually reach your SysML v2 endpoint, connect it to your MCP client and call the `ping` tool. `ping` is the smallest tool in the registry: it does a live round trip to the endpoint's commit list and reports whether the connection is healthy.

A working response looks like:

```json
{"up": true, "api_version": null, "commit_count": 0}
```

If `ping` fails, recheck `SYSMLV2_BASE_URL` and `SYSMLV2_TOKEN` before anything else: nearly every install problem traces back to one of those two.

## Next steps

- `docs/configuration.md` for the full environment variable reference.
- `docs/usage.md` for walked examples of the core workflows.
- `docs/TOOL-REFERENCE.md` for the complete tool list.
