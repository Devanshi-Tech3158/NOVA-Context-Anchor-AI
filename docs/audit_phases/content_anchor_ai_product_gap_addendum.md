# Content Anchor AI — Frontend Product-Gap Addendum

## Confirmed from the uploaded `nova-main(1).zip` snapshot

The archive contains a Python/FastAPI application and benchmark tooling, but no frontend source, frontend package manifest, browser UI assets, or browser-test setup. This is a missing product capability; it does not mean any frontend behavior was tested.

The visible API in `nova/api/main.py` exposes:

- `POST /ingest` — ingest messages.
- `POST /ask` — answer a question.
- `POST /verify` — verify a draft answer.
- `GET /audit/{id}` — read one audit record.
- `GET /healthz` — liveness-style status response.

The visible API does not provide a memory list/search endpoint, session/history endpoint, export/delete workflow, or account-management API. Phase 5 must not fabricate these capabilities. A Memory Library should be included only if a real authorized endpoint is added and tested.

## New UI implementation scope

See `content_anchor_ai_phase_5.md` for the full implementation brief. In summary, create a polished responsive user interface for Ingest, Ask, Verify, and Audit workflows, with typed API integration, claim/evidence display, accessibility, meaningful empty/loading/error states, and browser-level tests. The visual direction is premium, calm, editorial, and evidence-first rather than a generic AI-chat template.

## Security and provider constraints

- Do not replace `FakeLLM` in `nova/api/main.py`; real-provider integration is deferred to the project owner. Clearly disclose the placeholder provider in UI/help/diagnostics and do not imply that responses came from a real model.
- Never embed a deployment-wide API key in client JavaScript, public build environment variables, source maps, local storage, or session storage. Hosted deployment needs real session authentication or a trusted server-side BFF/proxy.
- CORS is not authentication. The UI must respect backend owner/tenant authorization.
- Do not ship fake metrics, seeded production records, nonfunctional controls, or backend functionality that does not exist.
