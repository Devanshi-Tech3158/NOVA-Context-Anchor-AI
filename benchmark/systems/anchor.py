"""Anchor system adapter interfacing with Context Anchor pipeline."""

import time
from typing import Any

from benchmark.counting_llm import CountingLLM
from benchmark.schema import Case
from benchmark.systems.base import Result


class AnchorSystem:
    """System adapter evaluating benchmark cases using Context Anchor pipeline."""

    def __init__(self, anchor: Any, llm: CountingLLM | None = None) -> None:
        """Initialize Anchor system with pipeline instance and optional counting LLM."""
        self.anchor = anchor
        self.llm = llm

    def run(self, case: Case) -> Result:
        """Ingest all sessions and invoke Anchor.ask to produce verified decision."""
        t0 = time.perf_counter()

        for session in case.sessions:
            if session:
                sess_id = session[0].session_id
                self.anchor.ingest(sess_id, session)

        decision = self.anchor.ask(case.question, draft_answer=case.draft_answer)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        retrieved_ids: list[str] = []
        for verdict in getattr(decision, "verdicts", []):
            for mid in getattr(verdict, "memory_ids", []):
                if mid not in retrieved_ids:
                    retrieved_ids.append(mid)
                if hasattr(self.anchor, "store"):
                    mem = self.anchor.store.get(mid)
                    if mem and getattr(mem, "source_msg_id", None):
                        src_id = mem.source_msg_id
                        if src_id not in retrieved_ids:
                            retrieved_ids.append(src_id)

        answer = getattr(decision, "final_answer", None) or ""
        action = getattr(decision, "action", "answer")

        prompt_tokens = self.llm.prompt_tokens if self.llm else 0
        completion_tokens = self.llm.completion_tokens if self.llm else 0

        return Result(
            answer=answer,
            action=action,
            retrieved_ids=retrieved_ids,
            latency_ms=elapsed_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
