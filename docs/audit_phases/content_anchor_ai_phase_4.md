# Content Anchor AI — Phase 4 Implementation Document

**Purpose:** A standalone implementation brief for Phase 4.

**Baseline:** Audit of `nova-main(1).zip`. The prior audit reported 208 passing tests, approximately 91% statement coverage, successful Python compilation and wheel build, and 19 resource warnings. Re-run checks on the working branch; do not assume these baseline results will still apply after changes.

**Important scope constraint:** Do **not** replace the default `FakeLLM` integration in `nova/api/main.py` with a real AI provider in this phase. That is deliberately deferred. Keep unrelated changes out of this phase unless required for its acceptance criteria. Do not delete tests merely to make the suite pass.

---

# Phase 4 — Repository hygiene, configuration clarity, packaging, and release readiness

**Goal:** Make the backend straightforward to install, configure, test, package, deploy, and support.

### Findings to fix

41. **Generated files and caches tracked** — `.gitignore`; tracked `benchmark/.cache/*.json` and generated directories. Ignore and untrack Python bytecode, pytest/Ruff caches, `.env` (while keeping `.env.example`), local databases, `.coverage`, `build/`, egg-info, benchmark caches/results, and other generated artifacts.
42. **Missing top-level README** — Add installation, configuration, run, test, benchmark, migration, deployment, and limitation instructions.
43. **Stale `CLAUDE.md`** — It says `Anchor.ask()`/`Anchor.verify()` are stubs and verification service is missing, despite their implementation. Update it to reflect the current architecture and status; keep `AGENTS.md` consistent.
44. **Development tools mixed into runtime dependencies** — `pyproject.toml:8-16`. Move pytest/Ruff and test-only dependencies into a development optional dependency group; establish a supported dependency/version policy and verify clean installs in CI.
45. **Misleading/unused configuration** — `nova/core/config.py:11-31`; `nova/api/main.py:49-57`; `nova/store/sqlite_store.py:21-35`. Wire settings that are meant to work or explicitly document/remove unsupported settings. Do not implement the deferred real API provider in this phase.
46. **Schema version constant/migrations unused** — `nova/store/sqlite_store.py:19, 39-88`. Use `SCHEMA_VERSION`, implement ordered migrations, and reject database schemas newer than the application supports.
47. **Protocol/API contracts inconsistent** — `nova/core/protocols.py:18-44`; `nova/store/sqlite_store.py:139-174`. Align public protocol methods with actual supported operations and document backend limitations.
48. **Wheel/package contents need a deliberate decision** — wheel build succeeds, but `benchmark` is not included in the built wheel. Decide whether benchmark tooling is development-only; document or package it intentionally.
49. **Lint/format CI not verified locally** — Ruff was unavailable in the audit environment. Install declared development tools in CI and run the configured lint/format gates.
50. **Audit output and resource warnings** — the coverage run emitted 19 ResourceWarnings, primarily unclosed SQLite connections. After Phase 2 lifecycle fixes, rerun tests with warnings visible and resolve regressions.
51. **No final release checklist** — document supported Python version, environment variables, database backup/migration/recovery, auth mode, audit retention, readiness checks, and known limitations. Do not claim multi-tenant or real-model readiness until those capabilities are implemented and tested.


### Phase 4 verification

- A clean checkout can install from documented instructions and run tests.
- Generated caches and local secrets are not tracked; scan current files and history as appropriate for secrets.
- README and agent instructions match the actual implementation.
- Wheel contents match the intended distribution.
- CI runs backend tests, benchmark smoke tests, lint/format checks, and packaging/build checks.
- No unexpected SQLite resource warnings remain.
- The application fails clearly on unsupported configuration or future database schema versions.

**Exit criteria:** A new developer can reproduce the backend environment; configuration and packaging are intentional; CI validates tests and build artifacts; and known product limitations are clear to developers and operators.

---

## Instructions for the coding agent

1. Work on a separate Git branch and preserve the original repository/archive.
2. Inspect the current code before editing; line numbers in audit findings may have shifted.
3. Fix the findings in this phase and add focused regression tests for each repaired defect.
4. Run targeted tests after each fix, then run the full test suite. Run Ruff and build checks when available.
5. Report changed files, commands executed, test results, unresolved issues, and any behavior that remains intentionally unsupported.
6. Do not mark the phase complete unless all exit criteria above are satisfied.
