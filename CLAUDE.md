# SEAcircos

Building a SEA-PHAGES-optimized fork of [phold-plot-wasm-app](https://gbouras13.github.io/phold-plot-wasm-app/)
so undergrads can generate circos plots of their phage genomes from their own
hand-curated functional annotations. Full project context, decisions, and
current status live in [PROGRESS.md](PROGRESS.md) — read that before starting
work here, and update it as work progresses.

## Memory system

A local MCP knowledge-graph memory server (`@modelcontextprotocol/server-memory`,
configured as `memory`) is connected in this environment and shared with the
user's Claude Desktop app — it persists across sessions and across projects.

- You have standing permission to use it proactively, without asking first:
  read from it (`search_nodes` / `read_graph` / `open_nodes`) whenever prior
  context would help, and write to it (`create_entities` / `add_observations`
  / `create_relations`) whenever you learn a durable fact, decision, or
  preference worth remembering later — project or otherwise.
- Entities already in the graph relevant to this project: `User`,
  `SEA-PHAGES program`, `SEAcircos`, `phold-plot-wasm-app`. Extend these
  (add_observations) rather than creating duplicates for the same thing.
- Reserve it for facts that outlive this repo or this conversation (decisions,
  preferences, standing project goals) — not in-progress task state, which
  belongs in PROGRESS.md, and not things trivially re-derivable by reading the
  code.
