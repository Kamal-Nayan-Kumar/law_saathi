# ADR-0001 — LangGraph 5-node agent with verify-retry loop

Status: accepted.

Context: Viva needs a visible agentic workflow (understand → plan → retrieve → verify → respond), solo build.

Decision: LangGraph with 5 nodes (intent, planner, tools, verifier, response) + shared memory; verifier can loop back to retrieval.

Consequences: More nodes to build, but tracing via LangSmith stays clean and the viva diagram matches code.
