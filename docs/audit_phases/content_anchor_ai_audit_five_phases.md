# Content Anchor AI — Five-Phase Remediation Plan

## How to use this plan

Run the phases in order and give your coding agent one phase at a time along with the project repository/archive. Phases 1–4 retain their original scope. **Phase 5 is the new, separate frontend phase**; it does not move UI implementation into Phases 1–4.

The baseline audit was performed against `nova-main(1).zip`. Previously reported baseline results were 208 passing tests, approximately 91% statement coverage, a successful Python compilation and wheel build, and 19 resource warnings. Re-run all checks on the working branch; these numbers are not a guarantee about the current code.

## Phase map

1. **[Phase 1 — Critical correctness, memory integrity, and access isolation](content_anchor_ai_phase_1.md)**
   Fix temporal ingestion and supersession, tenant isolation, fail-open authentication, evidence verdict semantics, correction selection, trust boundaries, injection resistance, quote validation, and memory ID collisions.

2. **[Phase 2 — Persistence, transactions, validation, and API reliability](content_anchor_ai_phase_2.md)**
   Fix embedding persistence, transaction atomicity, SQLite connection lifecycle, malformed extraction handling, timestamp normalization, schemas, API limits, retrieval constraints, vector compatibility, protocol contracts, audit privacy, errors, readiness, lookup ambiguity, and temporal policy.

3. **[Phase 3 — Benchmark correctness, CI safety, and evaluation reliability](content_anchor_ai_phase_3.md)**
   Fix workflow input injection risk, misleading benchmark modes, system initialization failures, correctness metrics, error/abstention conflation, scenario generation, historical queries, caching, claim splitting, token/cost reporting, and scenario validation.

4. **[Phase 4 — Repository hygiene, configuration clarity, packaging, and release readiness](content_anchor_ai_phase_4.md)**
   Fix generated artifacts, README and agent guidance, dependency groups, unused configuration, schema migrations, protocol alignment, packaging decisions, lint/format gates, resource warnings, and release documentation.

5. **[Phase 5 — Beautiful frontend and end-to-end product experience](content_anchor_ai_phase_5.md)**
   Build a polished responsive React/TypeScript UI for Ingest, Ask, Verify, and Audit workflows, with typed API integration, clear evidence/verdict presentation, accessible interactions, beautiful loading/empty/error states, and end-to-end tests. This is new product work because the audited archive has no frontend.

## Product gap note

The audited snapshot is a Python/FastAPI backend and benchmark suite, not a complete user-facing application. It exposes `POST /ingest`, `POST /ask`, `POST /verify`, `GET /audit/{id}`, and `GET /healthz`. There is no frontend in the snapshot, and no obvious memory listing/search, export, deletion, session/history, or account-management API. Phase 5 must not fabricate those functions; a Memory Library can appear only if a real authorized backend endpoint is implemented.

## Constraints for every phase

- **Do not replace or reconfigure the default `FakeLLM` integration in `nova/api/main.py`.** The project owner will add a real AI provider later.
- Do not delete or weaken tests merely to make the suite pass. Add regression tests for fixed defects.
- Do not trust a tenant/owner ID supplied only in an untrusted request body.
- Never expose a shared server API key in frontend JavaScript, public build variables, browser storage, or source maps.
- Do not misrepresent fake-provider behavior, fabricated data, benchmark estimates, or unsupported product capabilities.
- After every phase, report changed files, commands run, test/build results, unresolved issues, and intentionally unsupported behavior.
