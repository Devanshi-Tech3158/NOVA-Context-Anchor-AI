# Content Anchor AI — Phase 1 Implementation Document

**Purpose:** A standalone implementation brief for Phase 1.

**Baseline:** Audit of `nova-main(1).zip`. The prior audit reported 208 passing tests, approximately 91% statement coverage, successful Python compilation and wheel build, and 19 resource warnings. Re-run checks on the working branch; do not assume these baseline results will still apply after changes.

**Important scope constraint:** Do **not** replace the default `FakeLLM` integration in `nova/api/main.py` with a real AI provider in any phase. That is deliberately deferred to the project owner. Do not delete tests merely to make the suite pass.


---

# Phase 1 — Critical correctness, memory integrity, and access isolation

**Goal:** Stop memory corruption, incorrect answers, and unsafe access before any public or multi-user deployment.

### P0 findings to fix

1. **Temporal ingestion order** — `nova/pipeline.py:68-73`; `nova/temporal/supersession.py:46-60, 66-89`. Do not insert new memories as current before deciding their temporal status. Make classification, insertion, and supersession a coordinated operation.
2. **Cross-session/tenant supersession** — `nova/temporal/supersession.py:49-58`; `nova/store/sqlite_store.py:189-200`. Define memory ownership and the supersession key. Scope supersession to an authenticated owner/tenant and the intended entity/subject; decide explicitly whether same-owner memories can supersede across sessions.
3. **Multi-tenant isolation** — `nova/core/schemas.py:45-70`; `nova/api/main.py:21-57`; `nova/verification/service.py:55-91`. Add trusted user/tenant identity from authentication and enforce it for reads, writes, retrieval, supersession, and audit access. Do not trust a tenant ID supplied only in the request body. If the product remains strictly single-user/local, document that limitation and do not expose it as a shared service.
4. **Fail-open authentication** — `nova/api/main.py:42-47`. Require secure authentication configuration in production and fail startup when it is absent. Permit unauthenticated use only through an explicit local-development mode.
5. **Evidence verdict semantics** — `nova/verification/judge.py:66-82`. An existing memory ID is not proof. Enforce current-evidence requirements for supported/contradicted claims and validate successor relationships for outdated claims.
6. **Incorrect correction selection** — `nova/verification/decision.py:42-55`. Derive corrections from the validated supersession chain and relevant subject/entity, never from the first cited memory ID. Abstain if the current successor is ambiguous.
7. **Decision engine trust boundary** — `nova/verification/decision.py:65-90`. Validate verdict references and evidence before producing a final answer, even if another component supplied the verdict.
8. **Prompt injection / untrusted input** — `nova/extraction/extractor.py:39-42`; `nova/verification/service.py:80-86`; `nova/verification/claim_splitter.py:36-48`. Treat messages, retrieved memories, questions, and drafts as data; structure/escape them consistently and validate model output. Do not rely on prompt wording alone.
9. **Extraction quote does not prove claim** — `nova/extraction/quote_validator.py:24-59`. Validate the semantic relationship among quote, type, subject, and value; test contradictions, negation, questions, and proposed versus finalized decisions.
10. **Memory ID collisions/incorrect deduplication** — `nova/extraction/quote_validator.py:8-16`. Define idempotency explicitly, distinguish semantically different records, and compare existing payloads rather than silently ignoring a conflicting ID.


### Phase 1 regression tests

- Ingest out-of-order decisions through `Anchor.ingest()` and confirm exactly the intended current memory remains current.
- Two tenants with identical subjects but different values cannot retrieve or supersede one another's memories.
- Supersession rejects self-links, cycles, cross-owner links, and incompatible subjects/types.
- Supported claims cannot rely only on superseded or unrelated memories.
- Correction output remains correct regardless of the order of cited IDs.
- Malicious/instruction-like source messages cannot override system behavior or cause unsupported memories to be accepted.
- Genuine quotes paired with incorrect values or negation are rejected or flagged.

**Exit criteria:** Memory state remains correct through the public ingestion workflow; access boundaries are enforced; unsupported evidence cannot silently become a verified answer.

---

## Instructions for the coding agent

1. Work on a separate Git branch and preserve the original repository/archive.
2. Inspect the current code before editing; line numbers in audit findings may have shifted.
3. Fix the findings in this phase and add focused regression tests for each repaired defect.
4. Run targeted tests after each fix, then run the full test suite. Run Ruff and build checks when available.
5. Report changed files, commands executed, test results, unresolved issues, and any behavior that remains intentionally unsupported.
6. Do not mark the phase complete unless all exit criteria above are satisfied.
