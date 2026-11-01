"""FastAPI gateway exposing endpoints for memory ingestion, QA, and verification."""

from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

from nova.audit.logger import AuditError, AuditLog, AuditRecord
from nova.core.config import get_settings
from nova.core.llm import FakeLLM, GeminiLLM, HeuristicLLM, OpenAILLM
from nova.core.schemas import Decision, IngestReport, Message
from nova.extraction.extractor import ExtractionError, LLMExtractor
from nova.pipeline import Anchor
from nova.retrieval.embedder import HashEmbedder
from nova.retrieval.hybrid import HybridRetriever
from nova.store.sqlite_store import SqliteMemoryStore, StoreError
from nova.verification.claim_splitter import VerificationError

WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"


class IngestRequest(BaseModel):
    """Payload for memory ingestion."""

    session_id: str
    messages: list[Message]


class AskRequest(BaseModel):
    """Payload for question answering."""

    question: str
    draft_answer: str | None = None


class VerifyRequest(BaseModel):
    """Payload for answer verification."""

    question: str
    answer: str


def verify_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    """Validate optional X-API-Key header against environment configuration."""
    settings = get_settings()
    if settings.api_key and (not x_api_key or x_api_key != settings.api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def get_anchor() -> Anchor:
    """Dependency provider returning default Anchor instance."""
    settings = get_settings()
    store = SqliteMemoryStore(settings.db_path)
    embedder = HashEmbedder()
    retriever = HybridRetriever(store, embedder)

    # Pick LLM based on settings or keys
    if settings.gemini_api_key:
        model = settings.llm_model if settings.llm_model != "fake-model" else "gemini-1.5-flash"
        llm = GeminiLLM(settings.gemini_api_key, model=model)
    elif settings.openai_api_key:
        model = settings.llm_model if settings.llm_model != "fake-model" else "gpt-4o-mini"
        llm = OpenAILLM(settings.openai_api_key, model=model)
    elif settings.llm_provider != "fake":
        llm = HeuristicLLM()
    else:
        llm = FakeLLM()

    extractor = LLMExtractor(llm)
    audit_log = AuditLog(settings.db_path)
    return Anchor(store=store, extractor=extractor, retriever=retriever, audit_log=audit_log)


def create_app() -> FastAPI:
    """Create and configure FastAPI application instance with error handlers."""
    application = FastAPI(
        title="Nova API Gateway",
        description="Context Anchor: External source-linked memory + evidence-checked answers",
        version="0.1.0",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.exception_handler(ExtractionError)
    async def extraction_handler(request: Request, exc: ExtractionError) -> JSONResponse:
        return JSONResponse(
            status_code=422, content={"error": "ExtractionError", "detail": str(exc)}
        )

    @application.exception_handler(VerificationError)
    async def verification_handler(request: Request, exc: VerificationError) -> JSONResponse:
        return JSONResponse(
            status_code=422, content={"error": "VerificationError", "detail": str(exc)}
        )

    @application.exception_handler(StoreError)
    async def store_handler(request: Request, exc: StoreError) -> JSONResponse:
        return JSONResponse(status_code=500, content={"error": "StoreError", "detail": str(exc)})

    @application.exception_handler(AuditError)
    async def audit_handler(request: Request, exc: AuditError) -> JSONResponse:
        return JSONResponse(status_code=500, content={"error": "AuditError", "detail": str(exc)})

    @application.exception_handler(NotImplementedError)
    async def not_implemented_handler(request: Request, exc: NotImplementedError) -> JSONResponse:
        return JSONResponse(
            status_code=501, content={"error": "NotImplementedError", "detail": str(exc)}
        )

    @application.get("/")
    def root_endpoint(request: Request):
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            index_path = WEB_DIR / "index.html"
            if index_path.exists():
                return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
        return {
            "name": "Nova API Gateway",
            "version": "0.1.0",
            "hackathon": "Build With NOVA Hackathon",
            "status": "online",
            "docs_url": "/docs",
            "endpoints": {
                "ingest": "POST /ingest",
                "ask": "POST /ask",
                "verify": "POST /verify",
                "audit": "GET /audit/{id}",
                "healthz": "GET /healthz",
            },
        }

    @application.get("/app.js")
    def app_js_endpoint():
        js_path = WEB_DIR / "app.js"
        if js_path.exists():
            return HTMLResponse(
                content=js_path.read_text(encoding="utf-8"),
                media_type="application/javascript",
            )
        raise HTTPException(status_code=404, detail="File not found")

    @application.get("/preview.png")
    def preview_png_endpoint():
        img_path = WEB_DIR / "preview.png"
        if img_path.exists():
            return FileResponse(img_path, media_type="image/png")
        raise HTTPException(status_code=404, detail="Preview image not found")

    @application.post("/ingest", response_model=IngestReport)
    def ingest_endpoint(
        payload: IngestRequest,
        anchor: Annotated[Anchor, Depends(get_anchor)],
        _: Annotated[None, Depends(verify_api_key)],
    ) -> IngestReport:
        return anchor.ingest(payload.session_id, payload.messages)

    @application.post("/ask", response_model=Decision)
    def ask_endpoint(
        payload: AskRequest,
        anchor: Annotated[Anchor, Depends(get_anchor)],
        _: Annotated[None, Depends(verify_api_key)],
    ) -> Decision:
        return anchor.ask(payload.question, payload.draft_answer)

    @application.post("/verify", response_model=Decision)
    def verify_endpoint(
        payload: VerifyRequest,
        anchor: Annotated[Anchor, Depends(get_anchor)],
        _: Annotated[None, Depends(verify_api_key)],
    ) -> Decision:
        return anchor.verify(payload.question, payload.answer)

    @application.get("/audit/{id}", response_model=AuditRecord)
    def audit_endpoint(
        id: str,
        anchor: Annotated[Anchor, Depends(get_anchor)],
        _: Annotated[None, Depends(verify_api_key)],
    ) -> AuditRecord:
        record = anchor.get_audit(id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Audit record not found: {id}")
        return record

    @application.get("/healthz")
    def healthz_endpoint() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
