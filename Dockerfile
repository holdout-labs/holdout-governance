# Glama / container checks: build the package and run the MCP stdio server.
# Glama builds this image, starts it, and introspects via MCP stdio
# (initialize + tools/list) — `gov mcp` is the MCP stdio server.
FROM python:3.12-slim

WORKDIR /app

# Install the package with the MCP extra (jsonschema, pyyaml, mcp SDK).
COPY pyproject.toml MANIFEST.in README.md LICENSE ./
COPY src ./src
COPY schema ./schema
RUN pip install --no-cache-dir '.[mcp]'

# Newline-delimited JSON-RPC 2.0 over stdio. Glama runs this with stdin attached.
CMD ["gov", "mcp"]
