# Content Anchor AI — Phase 3 Implementation Document

**Purpose:** A standalone implementation brief for Phase 3.

**Baseline:** Audit of `nova-main(1).zip`. The prior audit reported 208 passing tests, approximately 91% statement coverage, successful Python compilation and wheel build, and 19 resource warnings. Re-run checks on the working branch; do not assume these baseline results will still apply after changes.

**Important scope constraint:** Do **not** replace the default `FakeLLM` integration in `nova/api/main.py` with a real AI provider in this phase. That is deliberately deferred to the project owner. Keep unrelated changes out of this phase unless required for its acceptance criteria. Do not delete tests merely to make the suite pass.

---

# Phase 3 — Benchmark correctness, CI safety, and evaluation reliability

**Goal:** Ensure benchmark and CI results are honest, reproducible, and secure, and that evaluation metrics reflect actual system behavior.

### Findings to fix

27. **GitHub Actions shell injection risk** — `.github/workflows/benchmark.yml`, `benchmark-full` command near lines 90-99. Pass workflow inputs through step-level `env`, quote variables in shell, validate numeric/enumerated inputs, and avoid interpolating untrusted values into command source.
28. **Fake benchmark mode mislabeled as real** — `benchmark/runner.py:145-151`. Do not replace the API's `FakeLLM`. Separately, make benchmark `--llm real` fail clearly as unimplemented or rename it until a genuine provider is supported; never report fake responses as real-model evaluation.
29. **Anchor benchmark system import failure** — `benchmark/runner.py:74-89`. The runner imports `MemoryExtractor`, while the implemented class is `LLMExtractor`; the error is swallowed and the requested system is skipped. Fix the import and fail loudly if a requested system cannot initialize.
30. **Incorrect correctness metric** — `benchmark/metrics.py:34-40`; `benchmark/report.py:58-67`. Compare expected action and answer content/grounding; handle negation; count correct abstention as correct for unanswerable cases.
31. **System errors disguised as abstentions** — `benchmark/runner.py:172-190`. Record explicit failures, don't assign zero latency to crashes, and make smoke/CI runs fail non-zero on system errors.
32. **Context-loss labels inaccurate** — `benchmark/scenarios.py`; `benchmark/systems/baseline.py:20-30`; `benchmark/metrics.py:68-73`. Ensure source facts marked “context dropped” are actually outside the baseline's context window, or compute the flag from the actual context supplied.
33. **Scenario/domain confounding** — `benchmark/generator.py:297-318`. Balance or independently seed/shuffle scenarios and domains so one scenario is not permanently paired with one domain.
34. **Decision-reversal generator fails on some seeds** — `benchmark/scenarios.py:260-294`. Bound reversal depth or append the reversal message; add deterministic multi-seed/property tests.
35. **Historical-query flag unused** — `benchmark/schema.py:43-47`; `benchmark/systems/anchor.py:19-29`; `nova/verification/service.py:76-90`. Define historical-query behavior and pass it through the system, distinguishing previous-value questions from current-value questions.
36. **Cache keys incomplete** — `benchmark/runner.py:31-58`. Include provider/model, prompt, JSON mode, and generation settings in cache identity; separate fake/real namespaces; corrupted entries should become cache misses.
37. **Claim splitter silently truncates at eight claims** — `nova/verification/claim_splitter.py:11, 30-33`. Raise a clear incomplete/too-many-claims outcome or safely support a defined limit; never imply the whole answer was verified after truncation.
38. **Single-sentence compound claims bypass splitting** — `nova/verification/claim_splitter.py:36-43`. Detect compound assertions or split them before verification.
39. **Benchmark token/cost metrics misleading** — `benchmark/counting_llm.py:52-77`; `benchmark/metrics.py:177-191`; `benchmark/systems/anchor.py:14-18, 43-55`. Mark token counts as estimates where appropriate, wire counters into AnchorSystem, and report unknown model cost as unknown rather than zero.
40. **Benchmark scenario validation coverage** — `benchmark/scenarios.py` and `benchmark/generator.py`. Add seeded multi-run checks for required message IDs, expected actions, source placement, split validity, and scenario/domain balance.


### Phase 3 regression tests

- Workflow inputs containing shell metacharacters cannot execute commands; invalid values are rejected.
- `--systems anchor` initializes; a requested system never silently disappears.
- `--llm real` fails clearly until genuine provider support exists.
- Wrong action, negation, correct abstention, and unanswerable cases are scored correctly.
- Exceptions are recorded as failures and make CI smoke runs fail.
- Across hundreds of seeds, generated cases validate and context-loss labels are true.
- Every scenario is tested across multiple domains.
- Historical questions exercise historical retrieval behavior.
- Cache entries cannot be reused across incompatible model/configuration modes.
- Long/compound answers are not silently only partially verified.

**Exit criteria:** Benchmark scores represent actual system behavior; generated cases are valid; system failures remain visible as failures; and CI cannot be manipulated through workflow inputs.

---

## Instructions for the coding agent

1. Work on a separate Git branch and preserve the original repository/archive.
2. Inspect the current code before editing; line numbers in audit findings may have shifted.
3. Fix the findings in this phase and add focused regression tests for each repaired defect.
4. Run targeted tests after each fix, then run the full test suite. Run Ruff and build checks when available.
5. Report changed files, commands executed, test results, unresolved issues, and any behavior that remains intentionally unsupported.
6. Do not mark the phase complete unless all exit criteria above are satisfied.
