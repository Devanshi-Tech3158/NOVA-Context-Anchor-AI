# Content Anchor AI / Nova Repository Audit

**Audited archive:** `nova-main(1).zip`  
**Scope:** Python application, tests, benchmark suite, GitHub Actions workflows, packaging/configuration, repository instructions and ZIP hygiene.  
**Audit date:** 2026-10-25

## Executive summary

The uploaded archive is more complete than the earlier snapshot: it contains a real verification service and **208 passing tests**. I ran the test suite, coverage, compilation, wheel build, and targeted reproductions. Passing tests are encouraging, but they do not mean the full application or benchmark is correct.

### Verification results

- `python -m pytest -q`: **208 passed**.
- `python -m pytest -q --cov=nova --cov=benchmark --cov-report=term-missing`: **208 passed**, approximately **91% statement coverage** across `nova` and `benchmark`; this run exposed **19 ResourceWarnings**, mainly unclosed SQLite connections.
- `python -m compileall -q nova benchmark tests`: passed.
- `python -m pip wheel . --no-deps --no-build-isolation`: built a wheel successfully. The built wheel contains the `nova` package but not the `benchmark` package; confirm whether benchmark utilities are intended to ship with the distribution.
- Ruff could not be run in this environment because Ruff is not installed and package installation was unavailable. Therefore the configured CI lint/format gates remain unverified.
- No common live API-key/private-key patterns were found in the tracked text files by a basic pattern scan. This is not a full secret-history audit.

I also reproduced multiple logic failures with targeted scripts. The most important are the temporal ingestion bug, embedding persistence loss, extraction `KeyError`, uppercase JSON fence parsing, wrong correction generation, and negative retrieval-limit behavior.

> **Scope note:** Per the owner's earlier instruction, this report does not ask the coding agent to replace the default `FakeLLM` in `nova/api/main.py`; that provider integration is deliberately deferred. I do separately flag the benchmark's `--llm real` option because it currently also runs a fake model and makes benchmark results misleading.

## P0 — Fix before any public or multi-user deployment

### 1. Ingestion inserts memories before deciding their temporal status

**Location:** `nova/pipeline.py:68-73`; `nova/temporal/supersession.py:46-60, 66-89`  
**Status:** Reproduced.

`Anchor.ingest()` inserts every `new_memory` as current using `store.add_many()` and only afterwards calls `apply_supersession()`. The temporal code's “new memory” branch is therefore bypassed for newly ingested memories. In the `existing` branch, an already-stored older memory is not marked superseded when a newer current memory exists.

**Reproduction:** Store a current PostgreSQL memory dated Jan 2, then insert a MySQL memory dated Jan 1 and run the same supersession path. Both remain current with no supersession link.

**Fix:** Make temporal classification and persistence one coordinated operation. Do not write new memories as current until their status and chain links have been determined. Add an end-to-end regression test through `Anchor.ingest()`, not just a unit test for `apply()`.

### 2. Embedding updates are not committed through the storage layer

**Location:** `nova/pipeline.py:75-84`  
**Status:** Reproduced.

The pipeline executes a raw SQL `UPDATE` for each embedding without an explicit transaction/commit. Closing a SQLite connection rolls back those pending updates.

**Reproduction:** Ingest a message, confirm its embedding blob exists on the open connection, close the connection, reopen the database, and read the row. The embedding is missing.

**Fix:** Add an explicit storage-layer method for writing embeddings with transaction handling. Commit atomically where possible. Test persistence after closing and reopening the database. Also test retry behavior if embedding generation fails after the memory row was committed; the retry must fill missing embeddings rather than permanently skip them.

### 3. Memory supersession is not scoped to an owner or a well-defined state key

**Location:** `nova/temporal/supersession.py:49-58`; `nova/store/sqlite_store.py:189-200`  
**Status:** Cross-session side effect reproduced; intended scope needs a product decision.

Supersession queries use `subject` alone. `current_by_subject()` likewise searches all current rows for that subject without an owner boundary. A decision in one session can supersede a matching subject from another session.

**Reproduction:** Session A stores `database = PostgreSQL`; Session B stores `database = MySQL` at a later time. The current PostgreSQL memory becomes superseded by Session B's MySQL memory.

**Important design nuance:** The benchmark intentionally tests retrieval across sessions, so simply adding `session_id` everywhere may break a desired feature. The correct fix is to define memory ownership (at least a `user_id`/`tenant_id` for multi-user operation), then scope supersession by owner plus a well-defined subject/entity key. Decide explicitly whether same-owner memories should supersede across sessions. Add two-tenant isolation tests.

### 4. Authentication is fail-open when no API key is configured

**Location:** `nova/api/main.py:42-47`  
**Status:** Directly visible in code.

If neither `NOVA_API_KEY` nor `API_KEY` is set, `verify_api_key()` allows every request. Forgetting one environment variable can silently expose `/ingest`, `/ask`, `/verify`, and `/audit/{id}` without authentication.

**Fix:** Require the key (or another real auth mechanism) in production and fail startup if secure production configuration is missing. Allow unauthenticated operation only in an explicitly selected local-development mode. Use per-user/tenant authorization if this will be a SaaS. `/healthz` can remain intentionally public if that is the deployment policy.

### 5. The benchmark workflow interpolates user-controlled inputs directly into shell commands

**Location:** `.github/workflows/benchmark.yml`, `benchmark-full` command near lines 90-99.

`workflow_dispatch` input values such as `seed`, `n`, `split`, `systems`, and `llm` are inserted directly into a `run:` shell script using GitHub expressions. These are user-controlled strings; shell metacharacters or command substitutions can become executable shell syntax. The same job exposes API-key secrets as environment variables.

**Fix:** Pass input values through step-level `env:` variables, reference them as quoted environment variables in the shell, and validate numeric/enumerated values in Python. Use fixed `choices` for fields such as `split`/`llm` where possible. Avoid expression interpolation into command source.

### 6. The judge accepts semantically invalid evidence labels

**Location:** `nova/verification/judge.py:66-82`  
**Status:** Visible logic gap.

`_check()` verifies that memory IDs exist, but a `supported` verdict is not required to cite a **current** memory. A superseded memory can be accepted as support. Similarly, `contradicted` is not required to be grounded in a current memory, despite the prompt defining it that way. An existing ID alone does not prove that the memory supports or contradicts a claim.

**Fix:** Enforce status semantics in code. For `supported`/`contradicted`, require appropriate current evidence; for `outdated`, validate the complete successor relationship. Strengthen claim-to-evidence entailment checks and test unrelated IDs, superseded-only support, contradictory current memories, and malformed chains. Model output should be treated as untrusted input.

### 7. Extraction can crash on structurally incomplete but valid JSON

**Location:** `nova/extraction/extractor.py:55-81, 90-98`  
**Status:** Reproduced.

`_parse_items()` accesses required keys using `item["type"]`, `item["subject"]`, and `item["value"]`. `KeyError` is not in the caught exception list, so a JSON object missing any required field bypasses the repair retry and raises an unexpected exception.

**Reproduction:** A valid JSON array with a memory object missing `type` raises `KeyError('type')`.

**Fix:** Validate each object using a Pydantic schema before construction, catch schema-validation errors for the one allowed repair attempt, and keep unexpected programming errors visible. Add tests for missing fields, `null`, wrong types, `NaN` confidence, and unknown source IDs.

### 8. Correction output can select an unrelated memory

**Location:** `nova/verification/decision.py:42-55`  
**Status:** Reproduced.

`_correction()` uses `found[0]` from the verdict's list of valid memory IDs. It assumes the first cited ID is the outdated memory or its current successor. If an unrelated valid memory ID appears first, the correction can report the wrong value.

**Reproduction:** Citing an unrelated SQLite memory before a superseded MySQL memory made the final correction claim SQLite was the current database instead of PostgreSQL.

**Fix:** Resolve the outdated claim from a validated supersession chain and relevant subject/entity, not list order. If there is no unambiguous current successor, abstain or report ambiguity.

### 9. Multi-tenant data separation is absent from the memory/API model

**Location:** `nova/core/schemas.py:45-70`; `nova/api/main.py:21-57`; `nova/verification/service.py:55-91`.

There is a `session_id` but no explicit tenant/user identity in `Memory`, storage queries, API authorization, or verification retrieval. The API accepts one global configured API key. `ask()`/`verify()` retrieve across sessions without an owner filter. If this service will serve multiple customers, their memory stores can be mixed together.

**Fix:** Implement tenant/user identity from authenticated credentials; persist it with each memory and audit event; enforce it in every retrieval, supersession, audit lookup, and write query. Do not trust a tenant ID supplied only in the request body. If this is intentionally a single-user local application, document that limitation and do not expose it as a shared service.

## P1 — Correctness, reliability, and benchmark trustworthiness

### 10. `--llm real` does not use a real model

**Location:** `benchmark/runner.py:145-151`.

When `llm_mode != "fake"`, the runner creates `CachingLLM(_make_fake_llm())` and then wraps it in another cache. No real provider is initialized. The workflow supplies `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`, but the runner never uses them.

**Fix:** Until a real benchmark provider is implemented, reject `--llm real` with a clear error or rename the option. When implemented, use the configured provider and make cache keys include provider/model, prompt, JSON mode, and relevant generation settings. Do not reuse fake responses in real-mode runs.

### 11. The Anchor benchmark system cannot be created

**Location:** `benchmark/runner.py:74-89`.

The code imports `MemoryExtractor` from `nova.extraction.extractor`, but the actual class defined in that module is `LLMExtractor`. The import failure is swallowed and the Anchor system is skipped.

**Reproduction:** `python -m benchmark.runner --n 4 --split dev --systems anchor --llm fake --limit 2` prints the import warning and exits with `ValueError: No valid systems configured`.

**Fix:** Import the actual extractor class, add a smoke test for `--systems anchor`, and avoid silently dropping a requested system. If a configured system fails to initialize, fail the run clearly rather than producing results for a different set of systems.

### 12. Benchmark correctness ignores expected actions and treats unanswerable cases as always wrong

**Location:** `benchmark/metrics.py:34-40`; `benchmark/report.py:58-67`.

`check_correctness()` only checks whether `expected.key_fact` is a substring of the answer. It never compares `result.action` with `case.expected.action`. Therefore:

- A wrong action can be scored correct if the expected fact appears somewhere in the answer.
- A negated/wrong statement such as “it is not PostgreSQL” can score correct because the substring `PostgreSQL` is present.
- An unanswerable case has `key_fact=None`, so it is always scored incorrect in the per-scenario table even when the system abstains correctly.

**Fix:** Define scenario-aware correctness. Compare normalized actions where an action is expected and check answer content/grounding separately. Treat correct abstention as correct for unanswerable cases. Add tests for negation, wrong actions with correct text, and proper abstention.

### 13. Benchmark exceptions are converted into successful-looking abstentions

**Location:** `benchmark/runner.py:172-190`.

Any system exception is printed to stderr and converted to an empty answer, `abstain`, and `latency_ms=0.0`. The run can still exit successfully, and the metrics then treat a crash as an ordinary abstention. This can hide regressions and artificially improve latency or abstention metrics.

**Fix:** Record an explicit failed/error outcome, exclude failures from normal quality metrics or count them as failures consistently, and make smoke/CI benchmarks exit non-zero if a system crashes. Do not encode a failure as a real `abstain` action.

### 14. Benchmark context-loss labels are not always true

**Location:** `benchmark/scenarios.py` builders for buried facts, reversed decisions, paraphrases, and cross-session cases; `benchmark/systems/baseline.py:20-30`; `benchmark/metrics.py:68-73`.

Scenarios are marked `context_dropped=True`, but planted facts are placed at random depths. The baseline sees the last 20 messages. In a generated run with seed 7 and n=150, **11 of 86 cases** marked as context-dropped had their expected source message inside the baseline's last 20 messages. The context-loss accuracy metric therefore includes cases where the fact was not actually lost from the baseline context window.

**Fix:** Place the source outside the exact baseline window for every case labeled as context-dropped, or compute the flag dynamically from the actual context supplied to each system. Add validator checks proving the source is absent from the baseline window.

### 15. Scenario and domain are coupled in the generated benchmark

**Location:** `benchmark/generator.py:297-318`.

`scenario` is selected via `i % len(SCENARIOS)` and `domain` via `i % len(DOMAINS)`. Both lists have seven entries, so each scenario is permanently paired with one domain. In the seed-7 run, for example, buried facts always use PostgreSQL, contradicting drafts always use the archive bucket, and paraphrase cases always use the token format.

**Impact:** Scenario performance is confounded with domain vocabulary; the benchmark does not test each scenario across a diverse range of domains and can overstate generalization.

**Fix:** Select scenario and domain independently with a seeded, balanced schedule (or use a shuffled cross-product), and ensure every scenario appears across all/most domains in both splits.

### 16. Decision-reversal case generation can fail for valid seeds

**Location:** `benchmark/scenarios.py:260-294`.

`depth_rev` can be equal to or greater than `num_fillers`, but unlike the other builders, `build_decision_reversed()` has no fallback that appends the reversal message after the loop. Some generated cases therefore lack their required current/reversed message.

**Reproduction:** Generating n=7 across seeds 0–499 failed validation for seeds **3, 191, 359, 381, and 434** because the expected reversal message ID was missing.

**Fix:** Bound the reversal depth to an index inside the loop or append the message if the selected depth is outside the loop range. Add a deterministic multi-seed/property test.

### 17. Historical-question flag is unused by benchmark systems

**Location:** `benchmark/schema.py:43-47`; `benchmark/systems/anchor.py:19-29`; `nova/verification/service.py:76-90`.

`Case.include_history` is populated by decision-reversal scenarios, but no benchmark system reads it. `Anchor.ask()` retrieves current memories only (`include_history=False`) when drafting an answer. A case asking “what was the previous value?” can therefore be evaluated as if it were an ordinary current-value question.

**Fix:** Define historical-query behavior explicitly and pass the mode through the relevant APIs/systems; then make the expected result match the documented semantics. Add a test for asking for the previous value versus the current value.

### 18. Cache keys are incomplete and real/fake caches can collide

**Location:** `benchmark/runner.py:31-58`.

The response cache key contains only the prompt SHA-1. It omits the `json` flag, provider/model, and generation parameters. Corrupt cache JSON also raises directly. Because the cache is shared, a response produced under one configuration can be reused under another.

**Fix:** Include all result-affecting parameters in the cache key, store cache metadata, handle corrupt entries as cache misses, and separate fake/real cache namespaces.

### 19. Claim splitting silently truncates answers after eight claims

**Location:** `nova/verification/claim_splitter.py:11, 30-33`.

The parser silently truncates to `MAX_CLAIMS = 8`. A longer answer can lose its later claims without any signal that the entire answer was not verified; the final decision is then built from only the claims that survived splitting.

**Fix:** Either support all claims under an explicit safe limit or return a “too many claims / incomplete verification” outcome. Never silently treat a partially examined answer as fully verified.

### 20. Single-sentence fast path skips atomic-claim splitting

**Location:** `nova/verification/claim_splitter.py:36-43`.

Any answer counted as one sentence bypasses the LLM splitter, even if it contains multiple independent assertions joined by commas, semicolons, or “and”. A judge may mark a compound claim supported because only part of it matches evidence.

**Fix:** Use a deterministic compound-claim check or always split when the text contains multiple assertion clauses. Test compound single-sentence answers.

### 21. JSON fence parsing fails for uppercase language labels

**Location:** `nova/verification/claim_splitter.py:20-22`.  
**Status:** Reproduced.

The regular expression only accepts lowercase `[a-z]*`, so a fenced response beginning with ` ```JSON ` remains uncleaned and raises `JSONDecodeError`.

**Fix:** Make fence parsing case-insensitive and cover uppercase, lowercase, unlabeled, and unfenced JSON.

### 22. Retrieval input and vector validation are incomplete

**Location:** `nova/retrieval/hybrid.py:48-97`; `nova/retrieval/embedder.py:23-30, 33-71`.

- Negative `k` values use Python negative slicing and return “all but the last item” instead of rejecting the request. Reproduction: `k=-1` returned 2 of 3 memories.
- There is no dimension or embedding-model metadata/check before taking the vector dot product. Changing from 256-dimensional hash vectors to a neural embedder (or changing models) can cause dimension errors or mix incompatible vector spaces.
- Missing embeddings are recomputed on the fly, but their persisted vector remains missing.
- `HashEmbedder(dimension=0)` is not rejected and causes a modulo-by-zero failure.
- The API currently constructs `HashEmbedder`, which is a deterministic hash/trigram feature representation, not a semantic embedding model. Paraphrase retrieval quality should not be assumed.

**Fix:** Validate `k > 0` and a maximum; validate positive embedder dimensions; persist model ID, version, and dimensions; reject/rebuild incompatible vectors; use a real semantic embedder for production and benchmark the retrieval quality.

### 23. Retriever is tied to SQLite internals despite accepting a generic store protocol

**Location:** `nova/retrieval/hybrid.py:21-46`.

Candidate enumeration relies on `store.conn` and the private `_row_to_memory()` method. If a different class correctly implements the public `MemoryStore` protocol but doesn't expose those SQLite internals, retrieval silently returns an empty list.

**Fix:** Add a public store method for retrieving candidate memories and embedding blobs, or narrow the protocol/type to SQLite explicitly. Do not silently return an empty result for unsupported storage implementations.

### 24. Supersession storage method permits invalid links

**Location:** `nova/store/sqlite_store.py:213-239`.

`supersede(old_id, new_id)` checks that both IDs exist but does not reject identical IDs, cross-owner links, mismatched subject/type, or invalid time direction. A self-supersession can mark a memory superseded and point it to itself, creating a cycle. The table has no foreign-key constraint for `supersedes_id`, despite enabling foreign keys on the connection.

**Fix:** Validate old/new are distinct and compatible, prevent cycles, verify ownership/state and temporal policy, and add database integrity constraints where appropriate. Add tests for self-link, cycle, missing parent, wrong subject, and cross-tenant link.

### 25. Supersession transaction is not guaranteed atomic

**Location:** `nova/temporal/supersession.py:94-102` together with `nova/store/sqlite_store.py:108-174, 213-239`.

`apply()` wraps the operation in `with store.conn`, but store methods called inside it have their own connection context managers. Nested connection contexts can commit at inner exits, so a later failure may leave part of a multi-step supersession chain committed despite the “single transaction” docstring.

**Fix:** Put transaction ownership in one layer. Make store operations support an existing transaction or implement one store-level method that applies the whole chain atomically. Add injected-failure tests that prove rollback of all intermediate changes.

### 26. Timestamp handling is inconsistent

**Location:** `nova/core/schemas.py:45-70`; `nova/store/sqlite_store.py:90-106, 189-211`; `nova/temporal/supersession.py:55-58, 71-89`.

Naive and timezone-aware datetimes are both accepted. Comparing one with the other can raise `TypeError`. `current_by_subject()` orders ISO timestamp strings lexicographically, which is not necessarily chronological when offsets differ. Timestamp ties have no deterministic SQL tiebreaker.

**Fix:** Normalize input timestamps to UTC (or reject naive values), compare parsed instants, and use stable ordering such as timestamp plus ID. Add mixed-offset and tie tests.

### 27. Schema validation allows invalid memory/message values

**Location:** `nova/core/schemas.py:45-70`.

The models permit blank subject/value/session/message IDs, arbitrary message roles, unbounded text, naive timestamps, and confidence values outside [0, 1]. I confirmed Pydantic accepts `confidence=float('nan')` in this model. Invalid values can poison retrieval/sorting or make stored confidence meaningless.

**Fix:** Add appropriate `Field` constraints and validators for non-empty identifiers/subjects/values, text lengths, allowed roles if applicable, finite confidence in [0, 1], and timezone-aware timestamps. Validate API input at the boundary.

### 28. Request sizes and text lengths are unbounded

**Location:** `nova/api/main.py:21-40`; `nova/core/schemas.py:62-70`.

Ingestion accepts an arbitrary message list and unbounded text; ask/verify accept unbounded questions and answers. This can cause memory usage spikes, slow requests, huge prompts, and unexpected provider cost when the real provider is wired.

**Fix:** Set per-field character limits, maximum messages per request, maximum serialized body size, and provider token budgets. Reject oversized requests with 413/422 responses.

### 29. API database connections are leaked per request

**Location:** `nova/api/main.py:49-57`; `nova/store/sqlite_store.py:241-256`; `nova/audit/logger.py:86-98`.

`get_anchor()` creates a new store and audit connection for every request, but no FastAPI dependency/lifespan cleanup closes them. `SqliteMemoryStore` has `close()`, but `AuditLog` has no close method. The coverage run emitted ResourceWarnings for unclosed SQLite connections, including API tests.

**Fix:** Manage long-lived resources through FastAPI lifespan or use yield dependencies with cleanup; add `AuditLog.close()` and ensure partial initialization failures also close resources. Test repeated requests and verify connection count does not grow.

### 30. API reports healthy even when dependencies are unavailable

**Location:** `nova/api/main.py:125-127`.

`/healthz` always returns `{"status":"ok"}` without checking database access or required configuration. This is a liveness endpoint, not a readiness check; deployment orchestrators can route traffic to an unusable instance.

**Fix:** Keep liveness lightweight, and add a separate readiness check for configured dependencies. Avoid exposing secrets or internal details in health output.

### 31. Error responses disclose internal exception details

**Location:** `nova/api/main.py:64-88`.

Handlers return `str(exc)` in the client response. Storage exceptions can include SQLite error details and paths; future provider errors may expose upstream diagnostics or sensitive request context.

**Fix:** Return stable public error codes and safe messages to clients; log detailed exceptions server-side with a request/correlation ID. Preserve 4xx/5xx distinctions.

### 32. Audit logging is not lifecycle- or privacy-complete

**Location:** `nova/audit/logger.py:75-97, 99-129`; `nova/verification/service.py:63-72`.

- AuditLog does not expose a close method and connections are not cleaned up by the API.
- The service does not pass token usage into `AuditRecord`, so `prompt_tokens` and `completion_tokens` remain zero/default even though the schema advertises them.
- Questions and answers are stored (truncated to 2,000 chars) without a retention/deletion policy or per-tenant access policy. Redacting exact configured API-key strings does not anonymize personal/business data or detect transformed/partial secrets.

**Fix:** Add resource cleanup, accurate usage instrumentation, retention/deletion rules, access control, and explicit privacy documentation.

## P2 — Maintainability, packaging, and data quality

### 33. Cache and generated files are committed / missing from `.gitignore`

**Location:** `.gitignore`; tracked `benchmark/.cache/*.json` files.

The archive includes `.git`, Python bytecode/cache folders, Ruff/Pytest caches, generated `nova.egg-info`, and 15 tracked benchmark response-cache files. `.gitignore` does not exclude benchmark cache/results/cases, `.env`, `.coverage`, `build/`, or local database files.

**Fix:** Add targeted ignores (`.env` while keeping `.env.example`, `*.db`, `.coverage`, `build/`, `.pytest_cache/`, `.ruff_cache/`, `__pycache__/`, `benchmark/.cache/`, and generated benchmark outputs). Remove generated caches from Git tracking. Share source using a clean archive; include `.git` only if history is explicitly needed.

### 34. No top-level README

The archive has no `README.md` explaining install, environment variables, running the API, expected provider configuration, migrations, test commands, benchmark semantics, or limitations.

**Fix:** Add a concise onboarding and operations README plus `.env.example` with placeholder values only.

### 35. `CLAUDE.md` is stale and contradicts the current code

**Location:** `CLAUDE.md`, especially the phase status and contracts sections.

It says `Anchor.ask()`/`Anchor.verify()` are stubs and the verification service does not exist, even though `nova/pipeline.py` and `nova/verification/service.py` implement them. It also says no Git history exists even though this archive has a Git repository and an initial commit. Stale instructions can cause coding agents to regress completed work.

**Fix:** Update or replace `CLAUDE.md` with the current architecture, implementation status, exact commands, and current constraints. Keep `AGENTS.md` aligned with it.

### 36. Runtime dependencies include development/test tools

**Location:** `pyproject.toml:8-16`.

`pytest`, `ruff`, and likely `httpx` (primarily needed for tests/TestClient) are listed as core dependencies. This adds unnecessary production installation weight and mixes test/lint tools with runtime requirements. Dependencies are not version-bounded or locked, so clean installs can change over time.

**Fix:** Keep actual runtime dependencies in `project.dependencies`, move test/lint packages into a `dev` optional dependency group, use an explicit supported version policy, and test clean installation in CI. A lock file is optional for a library but useful for reproducible deployment.

### 37. Configuration fields are unused or misleading

**Location:** `nova/core/config.py:11-18, 23-31`; `nova/api/main.py:49-57`; `nova/store/sqlite_store.py:21-35`.

`database_url`, `llm_provider`, `llm_model`, and provider API keys are defined and loaded but not wired into the relevant API/provider/storage construction. This can make operators believe selecting those environment variables changes runtime behavior when it does not. (This audit intentionally defers replacing the default API `FakeLLM`, per the owner's instruction.)

**Fix:** Wire supported settings into their implementations or remove/document unsupported fields. Validate unsupported configuration at startup instead of silently ignoring it.

### 38. Future database schema versions are not rejected

**Location:** `nova/store/sqlite_store.py:19, 39-88`.

`SCHEMA_VERSION` is declared but not used; migration logic hardcodes version 1. A database with a higher version is not explicitly rejected, and the code may proceed assuming an older schema.

**Fix:** Use the declared schema constant, implement ordered migrations, and fail clearly if the database schema is newer than the running code understands.

### 39. Memory IDs can collapse distinct semantic records

**Location:** `nova/extraction/quote_validator.py:8-16`.

The deterministic ID uses only the first 16 hexadecimal characters of SHA-1 over session/message/subject/value. The memory type, timestamp, and quote are not included. Two otherwise same-key records with different types can collide deterministically and `ON CONFLICT(id) DO NOTHING` silently preserves only the first inserted record. The 64-bit truncated ID also has finite collision risk at large scale.

**Fix:** Define the intended idempotency key explicitly. Include semantic fields that distinguish records or reject conflicting payloads for an existing ID; consider a longer digest or UUID scheme. Do not silently accept a collision as a duplicate without comparing stored fields.

### 40. Subject lookups and row ordering are under-specified

**Location:** `nova/store/sqlite_store.py:189-200`; `nova/temporal/supersession.py:46-60`.

`current_by_subject()` orders only by timestamp and returns a single memory, even when multiple current memories with the same subject but different types/owners exist. The temporal logic can therefore see a non-supersedable type first and leave a supersedable current decision untouched. Same-timestamp ordering is not deterministic.

**Fix:** Query by the explicitly defined owner/entity/state key and supersedable type set, return/validate multiple current matches instead of assuming one, and enforce the invariant that each mutable key has at most one current value.

### 41. `MemoryStore` protocol and implementation contract are inconsistent

**Location:** `nova/core/protocols.py:18-44`; `nova/store/sqlite_store.py:139-174`; `nova/retrieval/hybrid.py:21-46`.

The protocol exposes `add_many(memories)` only, while the implementation adds an optional embeddings parameter. More importantly, retrieval and supersession reach into private SQLite fields rather than relying on protocol methods. `add_many()` also silently accepts an embeddings list shorter/longer than the memories list and fills the missing entries with `None`.

**Fix:** Align the protocol with actual supported operations, validate the embedding-list length when provided, and keep SQLite-specific logic behind the store implementation.

### 42. Extraction and answer prompts do not consistently isolate untrusted text

**Location:** `nova/extraction/extractor.py:39-42`; `nova/verification/service.py:80-86`; `nova/verification/claim_splitter.py:36-48`.

Conversation messages, retrieved memory values/quotes, questions, and draft answers are interpolated into natural-language prompts. The judge uses JSON escaping for memory/claim fields, but the extraction and answer prompts do not consistently structure user content as data. A malicious or instruction-like source message can attempt to influence memory extraction or answer generation. Quote validation ensures a quote exists, not that the extracted value follows from it.

**Fix:** Delimit/JSON-encode untrusted content consistently, state that it is data not instructions, validate structured outputs, and add prompt-injection/adversarial extraction tests. Do not rely on prompting alone as a security boundary.

### 43. Quote validation only proves substring existence

**Location:** `nova/extraction/quote_validator.py:24-59`.

The validator confirms a normalized quote occurs in the source message. It does not require the quote to substantiate `type`, `subject`, or `value`; a short generic quote can be paired with an unrelated or contradictory value. It also does not impose a minimum useful quote length.

**Fix:** Add semantic consistency validation between extracted claim and quoted evidence, plus tests for genuine quotes paired with wrong values, negation, questions vs finalized decisions, and quote/subject mismatches.

### 44. Token and cost metrics are estimates or zeros, not dependable measurements

**Location:** `benchmark/counting_llm.py:52-77`; `benchmark/metrics.py:177-191`; `benchmark/systems/anchor.py:14-18, 43-55`.

`LLMClient.complete()` returns a string, so actual provider token usage is not available through the current protocol. `CountingLLM` estimates tokens as `len(text)//4`. The Anchor benchmark adapter is constructed without the `CountingLLM`, so its reported token counts are always zero. Unknown model names default to zero cost, which can present unpriced usage as free.

**Fix:** Define a usage-aware response type or provider instrumentation, pass the counter into AnchorSystem, mark estimated counts as estimates, and represent unknown cost as unknown instead of `$0`.

### 45. Generic facts/commitments may never supersede

**Location:** `nova/temporal/supersession.py:8-12`.

Only decisions, corrections, and preferences are supersedable. If a fact or commitment is intended to represent a mutable state (for example, a changed role, location, planned deadline, or revoked commitment), old and new versions may both remain current. This may be a design choice, but it must be explicit.

**Fix:** Define temporal policy per memory type and test updates/revocations for every type. Don't automatically make all types supersedable without deciding semantics.

## Recommended fix order

1. Fix ingestion/supersession ordering and memory ownership/tenant boundaries.
2. Commit embeddings through the store and close database connections safely.
3. Harden authentication defaults, request validation/limits, and the benchmark workflow shell inputs.
4. Make judge evidence semantics and correction generation deterministic and safe.
5. Fix the benchmark runner Anchor import, real-mode labeling, exception reporting, and correctness metrics.
6. Fix generator validity/context-loss/domain balancing and historical-query behavior.
7. Add schema/timestamp/vector validation and atomic supersession integrity tests.
8. Clean repository hygiene, update documentation, adjust dependency groups, and rerun CI with Ruff installed.

## Regression tests that should be added

At minimum, add tests for:

1. Late-arriving memory through the public `Anchor.ingest()` path.
2. Two tenants with the same subject but different values; neither can supersede or retrieve the other's memory.
3. Embeddings persist after closing/reopening SQLite and after retrying a failed embedding call.
4. Malformed JSON objects missing each required extraction field trigger repair or a typed error, never uncaught `KeyError`.
5. `supported` cannot cite only a superseded memory; `contradicted` must reference appropriate current evidence.
6. Unrelated cited IDs cannot control correction output, regardless of list order.
7. Empty/oversized API fields, oversized message lists, missing production API key, naive/mixed-offset timestamps, and invalid confidence values are rejected.
8. `k < 1`, zero/negative embedder dimensions, and mismatched embedding dimensions fail with clear typed validation errors.
9. `--systems anchor` initializes and runs; requesting an unsupported system never silently vanishes.
10. `--llm real` either calls a genuine provider or exits with a clear “not implemented” error.
11. Benchmark correctness validates both expected action and answer, including negation and correct unanswerable abstention.
12. Generator works across hundreds of seeds and guarantees the source is outside the baseline context for every context-loss case.
13. Benchmark exceptions are visible failures and cause CI smoke runs to fail appropriately.
14. API requests do not leak SQLite connections across repeated requests.
15. Supersession rejects self-links/cycles and rolls back all chain changes after injected failure.

## Final assessment

This is a promising prototype with useful separation of concerns and a meaningful test suite, but its current passing tests do not prove the critical workflow is correct. I would not call this production-ready yet. Fix the memory/state and tenant-boundary defects first, then the evidence-verification safeguards and benchmark validity issues. The fake provider in the API remains explicitly deferred as requested; everything else in this report should be reviewed before launch.
