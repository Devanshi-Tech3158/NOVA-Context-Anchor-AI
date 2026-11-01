# Content Anchor AI — Five Phase Documents

These documents retain the original four remediation phases and add **Phase 5 as a separate frontend phase**. Phases 1–4 remain focused on backend correctness/reliability, benchmark/CI trustworthiness, and repository/release readiness. UI implementation belongs in Phase 5.

Use one phase at a time, in order:

1. [Phase 1 — Critical correctness, memory integrity, and access isolation](content_anchor_ai_phase_1.md)
2. [Phase 2 — Persistence, transactions, validation, and API reliability](content_anchor_ai_phase_2.md)
3. [Phase 3 — Benchmark correctness, CI safety, and evaluation reliability](content_anchor_ai_phase_3.md)
4. [Phase 4 — Repository hygiene, configuration clarity, packaging, and release readiness](content_anchor_ai_phase_4.md)
5. [Phase 5 — Beautiful frontend and end-to-end product experience](content_anchor_ai_phase_5.md)

See [the master roadmap](content_anchor_ai_audit_five_phases.md) for the summary, dependencies, and scope constraints. The original audit is also included as `content_anchor_ai_full_audit.md`.

## Non-negotiable constraints

- Do not replace the default `FakeLLM` provider integration in `nova/api/main.py`; the project owner will handle the real-provider integration later.
- Do not fabricate API capabilities, memory records, dashboard metrics, or AI responses.
- Keep secrets server-side; never expose a shared server key in browser code or public build variables.
- Re-run tests after each phase and document any remaining issues.
