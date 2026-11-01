# Content Anchor AI — Phase 2 Implementation Document

**Purpose:** A standalone implementation brief for Phase 2.

**Baseline:** Audit of `nova-main(1).zip`. The prior audit reported 208 passing tests, approximately 91% statement coverage, successful Python compilation and wheel build, and 19 resource warnings. Re-run checks on the working branch; do not assume these baseline results will still apply after changes.

**Important scope constraint:** Do **not** replace the default `FakeLLM` integration in `nova/api/main.py` with a real AI provider in this phase. That is deliberately deferred to the project owner. Keep unrelated changes out of this phase unless required for its acceptance criteria. Do not delete tests merely to make the suite pass.

---

# Phase 2 — Persistence, transactions, validation, and API reliability

**Goal:** Ensure stored data survives restarts and malformed or oversized requests fail safely.

### Findings to fix

11. **Embedding persistence** — `nova/pipeline.py:75-84`. Move embedding writes into the storage layer, commit them, and coordinate memory/embedding writes safely. Retry must populate missing embeddings rather than skip a memory permanently.
12. **Atomic supersession transactions** — `nova/temporal/supersession.py:94-102`; `nova/store/sqlite_store.py:108-174, 213-239`. Give one layer ownership of the transaction; prove rollback of all chain changes when an intermediate operation fails.
13. **SQLite connection leaks** — `nova/api/main.py:49-57`; `nova/store/sqlite_store.py:241-256`; `nova/audit/logger.py:86-98`. Use FastAPI lifespan or yield dependencies with cleanup; add `AuditLog.close()` and clean up partial initialization.
14. **Malformed extraction JSON** — `nova/extraction/extractor.py:55-81, 90-98`. Validate objects with a schema before construction and handle validation errors in the bounded repair path. Avoid broad exception catches that hide programming bugs.
15. **Timestamp normalization and ordering** — `nova/core/schemas.py:45-70`; `nova/store/sqlite_store.py:90-106, 189-211`; `nova/temporal/supersession.py:55-58, 71-89`. Normalize timestamps to UTC or reject naive timestamps; use deterministic tie-breaking.
16. **Schema/input validation** — `nova/core/schemas.py:45-70`. Require non-empty identifiers and relevant fields, constrain confidence to finite `[0, 1]`, validate allowed roles if applicable, and define text-length limits.
17. **Unbounded API requests** — `nova/api/main.py:21-40`; `nova/core/schemas.py:62-70`. Add body-size, message-count, text-length, answer/question-length, and provider token-budget limits.
18. **Retrieval limits** — `nova/retrieval/hybrid.py:96-97`. Reject `k < 1` and cap excessive values rather than allowing Python negative slicing.
19. **Embedder configuration and vector compatibility** — `nova/retrieval/hybrid.py:48-97`; `nova/retrieval/embedder.py:23-30, 33-71`. Reject zero/negative dimensions; validate vector dimensions and embedding model/version; re-embed or reject incompatible vectors.
20. **Store/protocol contract mismatch** — `nova/retrieval/hybrid.py:21-46`; `nova/core/protocols.py:18-44`; `nova/store/sqlite_store.py:139-174`. Stop reaching into SQLite private fields from generic retrieval. Add public store methods or explicitly restrict the type to SQLite. Validate supplied embedding-list length.
21. **Supersession integrity** — `nova/store/sqlite_store.py:213-239`. Reject self-links, cycles, incompatible records, wrong owner/state, and invalid temporal direction. Add appropriate database integrity constraints.
22. **Audit privacy and completeness** — `nova/audit/logger.py:75-97, 99-129`; `nova/verification/service.py:63-72`. Define retention/deletion and tenant access policies, clean up connections, and record token usage only when genuinely available.
23. **Error response leakage** — `nova/api/main.py:64-88`. Return safe stable public error messages/codes; log detailed exceptions server-side with request/correlation IDs.
24. **Health/readiness distinction** — `nova/api/main.py:125-127`. Keep liveness lightweight and add a readiness check for required dependencies without leaking internals.
25. **Subject lookup ambiguity** — `nova/store/sqlite_store.py:189-200`; `nova/temporal/supersession.py:46-60`. Query by defined owner/entity/state key, handle multiple current matches explicitly, and use deterministic ordering.
26. **Memory type temporal policy** — `nova/temporal/supersession.py:8-12`. Define whether facts and commitments can change/revoke; test policy for each memory type rather than assuming all types behave alike.


### Phase 2 regression tests

- Embeddings survive closing/reopening SQLite and are recovered after a failed embedding call.
- Injected failure halfway through supersession rolls back the whole operation.
- Repeated API requests do not increase open database connections.
- Missing extraction fields trigger a bounded repair or typed error, never an uncaught `KeyError`.
- Mixed timezone offsets, naive timestamps, timestamp ties, NaN confidence, blank IDs, and invalid roles are handled deterministically.
- Oversized API requests and invalid retrieval parameters are rejected with clear 4xx responses.
- Incompatible embedding dimensions/models fail clearly rather than silently returning misleading results.
- Public error responses do not contain internal paths or raw database/provider exceptions.

**Exit criteria:** Persistent data is durable, transactions are atomic, request limits are enforced, malformed inputs fail safely, and resources are properly cleaned up.

---

## Instructions for the coding agent

1. Work on a separate Git branch and preserve the original repository/archive.
2. Inspect the current code before editing; line numbers in audit findings may have shifted.
3. Fix the findings in this phase and add focused regression tests for each repaired defect.
4. Run targeted tests after each fix, then run the full test suite. Run Ruff and build checks when available.
5. Report changed files, commands executed, test results, unresolved issues, and any behavior that remains intentionally unsupported.
6. Do not mark the phase complete unless all exit criteria above are satisfied.
