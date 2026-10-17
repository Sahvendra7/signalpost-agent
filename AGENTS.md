# Codebase Knowledge

This repository is indexed by Graphify. 
Do not use `grep` or text search to explore the codebase. 

Instead, ALWAYS use the following MCP tools:
- `query_graph` to search for components, semantic intent, or dependencies.
- `get_node` to read the full source code and metadata of a node found in the graph.

Example: If you need to know how "refresh" is handled, run `query_graph` with `query="refresh"`.
