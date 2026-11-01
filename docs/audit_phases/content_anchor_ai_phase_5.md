# Content Anchor AI — Phase 5 Implementation Document

**Purpose:** Build the missing frontend as a polished, genuinely usable product. This is a new feature phase, not a rewrite of Phases 1–4.

**Baseline:** The audited `nova-main(1).zip` snapshot contains a Python/FastAPI backend, tests, and benchmark tools, but no frontend source, frontend package manifest, or browser-test setup. Re-check the current branch before implementing.

**Non-negotiable scope constraint:** Do **not** replace or reconfigure the default `FakeLLM` integration in `nova/api/main.py`. The project owner will add a real model provider later. The UI must not imply that AI output is powered by a real model while `FakeLLM` is active. Do not fabricate data or controls for backend capabilities that do not exist.

---

# Phase 5 — Beautiful frontend and end-to-end product experience

**Goal:** Deliver a distinctive, responsive, accessible workspace for Content Anchor AI that makes ingestion, question answering, evidence verification, and audit lookup feel clear and trustworthy.

## 1. Visual direction: premium, calm, evidence-first

Avoid a generic AI-chat clone, neon gradients, overly rounded “template dashboard” cards, and decorative charts with no data behind them. The interface should feel like a considered knowledge-work product: calm, editorial, precise, and confidence-building.

### Design system

- **Core palette:** ink `#171923` for body text; midnight `#171B2D` for the navigation rail; porcelain `#F7F6F2` for the app canvas; white `#FFFFFF` for primary surfaces; border `#E6E5E1` for quiet dividers; indigo `#5146E5` for primary actions and focus; lavender `#ECEBFF` for selected/soft accent surfaces. Use the accent with restraint—avoid gradients as the main visual identity.
- **Semantic states:** Supported = forest `#176B4D` on pale green `#E8F5EE`; Outdated = ochre `#925B08` on pale amber `#FFF3D6`; Contradicted = deep red `#B42318` on pale rose `#FDECEA`; Unsupported = slate `#475569` on `#F1F3F6`; Error = deep red with a clear text explanation. Pair every color with a word label and icon; never rely on color alone.
- **Typography:** use Inter or Geist where available, with system sans-serif fallbacks. Use a clear type scale (compact labels, readable 14–16 px body, strong 24–32 px page headings); reserve any serif/display face for rare editorial accents only. Prefer local/system fonts so the app remains readable offline. Use tabular numerals for counts and timestamps where helpful.
- **Layout and spacing:** use a 4/8 px spacing rhythm, generous whitespace, clear section hierarchy, quiet borders, 10–14 px card radii, and restrained shadows only when they clarify layering. On wide desktop, use a roughly 236–252 px navigation rail and a content column capped near 1,200 px; on mobile collapse navigation into an accessible drawer/menu. Keep forms aligned and scannable.
- **Surface hierarchy:** separate the app canvas, primary work surface, and inset evidence blocks subtly; use thin borders and spacing before adding shadows. Keep the main question/answer content visually dominant over secondary metadata.
- **Icons:** use one consistent icon family (for example Lucide). Icons supplement labels; they must not replace accessible names.
- **Motion:** subtle 120–200 ms transitions for navigation, disclosure, and state changes. Respect `prefers-reduced-motion`; no parallax or distracting animations.
- **Content styling:** render evidence quotes with strong visual separation, source IDs in a compact monospace treatment, and claim verdicts as labeled chips/cards. Show why a claim received its verdict, not just the verdict badge. Avoid dense tables for the primary user workflows.

## 2. Frontend stack and repository layout

Inspect the current repository and owner constraints first. Since the audited snapshot has no frontend stack, if none is specified, create a self-contained `frontend/` app using **React + TypeScript + Vite**. Use a lightweight styling approach (Tailwind CSS or CSS modules/design tokens), a single icon set, and minimal dependencies. Choose component primitives that are accessible by default. Keep frontend scripts and dependencies separate from Python runtime dependencies.

Provide clear scripts for development, production build, lint, type-check, unit/component tests, and browser E2E tests. Commit a lockfile so installs are repeatable. Do not put server secrets or the deployment-wide API key into frontend environment variables, browser storage, built JavaScript, or source maps.

## 3. Information architecture and screens

Build a responsive application shell with a clear product wordmark, primary navigation, page titles, and a discreet connection/provider status area. Avoid showing user/account controls unless real authentication and account endpoints exist.

### A. Workspace landing page

- Present a useful welcome/header area and clear next-step actions: **Ingest conversation**, **Ask a question**, and **Verify an answer**.
- Show only trustworthy live counts or recent activity if the API actually provides them. If not, use a concise product explanation and workflow shortcuts—not fake metrics, sample production records, or made-up recent activity.
- Include a clear first-run empty state and a lightweight explanation of how memory evidence and verification statuses work.

### B. Ingest

- Build a well-designed conversation form with session ID and one or more message rows containing role, text, timestamp, and message ID where required by the actual API contract.
- Support adding/removing message rows, readable validation, paste-friendly text entry, and clear submit/loading/success/failure states.
- After success, show the API's real result counts and statuses (such as added, superseded, or dropped), including meaningful partial-success messaging. Do not silently alter what the user typed.
- Handle very long text and API validation limits gracefully; preserve user-entered form data after recoverable failures.

### C. Ask

- Provide an uncluttered question composer, with any optional draft-answer fields only if supported by the API.
- Present the actual response/action and separate it from evidence. Render claim-by-claim verdicts with clear labels, evidence references, rationale, and corrections when returned by the backend.
- Make it visually impossible to confuse Unsupported, Outdated, or Contradicted with Supported. Show abstention plainly and do not invent an answer where the backend did not return one.
- Provide helpful copy/copy-evidence controls only when they operate on actual returned values; include success feedback accessible to assistive technology.

### D. Verify

- Present the question and draft answer in a focused two-part form, followed by a structured verification report.
- Show each claim as a readable unit with the verdict, evidence IDs/quotes, explanation, and final overall decision.
- Preserve the original submitted answer in the result view so users can compare what was submitted against what the service checked. Be explicit about partial verification or claim limits.

### E. Audit lookup

- Provide a simple audit-ID search/lookup screen and a well-formatted record detail view.
- Handle not-found, unauthorized, network, and server errors without exposing stack traces or leaking whether another tenant's audit record exists.
- Minimize display of sensitive raw prompt/source text and respect the backend's access controls and retention policy.

### F. Memory library (conditional)

- Only include a browsable/searchable Memory Library if a real, authorized, owner-scoped memory-list/search API exists. If the backend does not provide one, do not render fake memory cards or a nonfunctional navigation item. Either keep it out of navigation or show a clearly marked “Not available in this API version” note in a product capabilities page.
- Do not add edit, delete, export, account management, history, settings, upload, analytics, or team UI unless the corresponding API behavior is implemented and tested.

## 4. API integration and state design

- Centralize all API calls in a typed client module. Use the backend OpenAPI schema as the source of truth when possible; otherwise define types and contract tests from actual request/response models.
- Configure only a public API base URL in frontend settings. Use a trusted same-origin BFF/proxy or a real authenticated session flow for hosted deployments. Never expose a shared static server key in a `VITE_*` variable or browser storage. A development proxy is acceptable only with explicit local-development documentation.
- Implement consistent handling for initial loading, pending submission, empty results, client validation, `400`/`401`/`403`/`404`/`429`/`5xx`, timeout, and offline/connection failure.
- Use request cancellation for navigational reads where appropriate. Do not automatically retry writes unless idempotency is guaranteed. Prevent double-submission while a write is in flight.
- Keep request/response logging privacy-conscious. Never log API keys, access tokens, or full user conversations by default.
- Show a truthful provider/status label, such as **Prototype provider · FakeLLM**, in an About/diagnostics area or compact status popover. Do not label the product “AI-powered by …” or imply real-model inference until the provider actually exists.

## 5. Responsive, accessible, and polished interactions

- Desktop: use a balanced two-column workspace where it helps evidence review; keep readable max-widths for long-form answers.
- Tablet/mobile: collapse navigation cleanly, stack panels, make touch targets comfortable, and ensure no horizontal overflow.
- Meet WCAG 2.2 AA intent: semantic landmarks/headings, visible keyboard focus, full keyboard operation, proper labels, associated field errors, sufficient contrast, screen-reader announcements for async states, and status labels that are not color-only.
- Every screen needs designed empty, loading/skeleton, success, validation, authorization, not-found, server-error, and offline states as relevant. No endless spinners or raw exception dumps.
- Add thoughtful microcopy and clear confirmation for any destructive operation—but don't add destructive controls unless supported by the API.
- Ensure the application looks complete at common widths (approximately 360 px mobile, 768 px tablet, and 1280–1440 px desktop), not only in a desktop screenshot.

## 6. Testing and completion gates

- Unit/component tests cover API client mapping, loading/error/empty states, form validation, verdict rendering, and responsive/navigation behavior.
- Browser E2E tests cover ingest → result, ask → evidence rendering, verify → claim verdicts, audit lookup, provider limitation labeling, offline/server error, authorization failures, and mobile navigation.
- Use deterministic API fixtures for UI tests, but do not treat fixtures as real integration evidence. Include at least one E2E smoke test against the local FastAPI app using its actual response contract.
- Verify no secret appears in the built bundle, source maps, local/session storage, or committed environment files.
- Run production build, lint, type-check, component tests, and E2E tests in CI. Capture a screenshot of each primary screen for review if the available tooling supports it, and do a visual QA pass at desktop and mobile widths.

## Phase 5 acceptance checklist

- [ ] Ingest, Ask, Verify, and Audit workflows are connected to actual backend endpoints.
- [ ] The interface has a coherent visual system, strong typography, deliberate spacing, consistent icons, and polished responsive states.
- [ ] Every backend verdict is presented with an explicit label and explanation; unsupported evidence is never presented as confirmed truth.
- [ ] No fake metrics, fake memory records, or nonfunctional controls are shipped.
- [ ] `FakeLLM` remains unchanged, and the product is transparent that provider behavior is currently a placeholder.
- [ ] No server-side secrets are delivered to the browser.
- [ ] Keyboard, screen-reader, contrast, and reduced-motion behavior are checked.
- [ ] Frontend build, lint, type-check, component tests, and browser smoke tests pass.
- [ ] The frontend has local setup instructions and a clear description of supported/unsupported capabilities.

---

## Instructions for the coding agent

1. Follow the plan in order: finish Phases 1–4 on their original backend, benchmark/CI, and repository/release scopes; then implement all frontend work in this separate Phase 5.
2. Work on a new branch and inspect the repository before choosing file layout. Preserve the backend architecture and tests.
3. Implement the real workflows, not static mockup-only pages. Fixtures are for tests and visual development only, not production data.
4. Do not change the default API `FakeLLM` provider integration; do not invent unsupported endpoints to make the UI appear more complete.
5. Report changed files, commands run, test results, visual QA outcomes, and known limitations. Do not call Phase 5 complete until the acceptance checklist passes.
