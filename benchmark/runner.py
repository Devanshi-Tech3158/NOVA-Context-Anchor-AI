"""Benchmark runner: evaluate systems against generated cases and emit results."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json as _json_mod
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from benchmark.generator import generate
from benchmark.metrics import compute_metrics
from benchmark.report import write_report
from benchmark.schema import Case, Split
from benchmark.systems.base import Result
from benchmark.systems.baseline import BaselineSystem
from benchmark.systems.rag import RAGSystem
from nova.core.llm import FakeLLM, LLMClient
from nova.retrieval.embedder import HashEmbedder

CACHE_DIR = Path("benchmark/.cache")
RESULTS_DIR = Path("benchmark/results")

ABSTAIN_ANSWER = "I do not have enough information to answer."


class CachingLLM:
    """LLM wrapper that caches responses on disk keyed by sha1(prompt)."""

    def __init__(self, inner: LLMClient, cache_dir: Path = CACHE_DIR) -> None:
        """Initialize caching wrapper around an LLMClient."""
        self.inner = inner
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.hits: int = 0
        self.misses: int = 0

    def _cache_path(self, prompt: str) -> Path:
        key = hashlib.sha1(prompt.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{key}.json"

    def complete(self, prompt: str, *, json: bool = False) -> str:
        path = self._cache_path(prompt)
        if path.exists():
            self.hits += 1
            data = _json_mod.loads(path.read_text(encoding="utf-8"))
            return data["response"]
        self.misses += 1
        response = self.inner.complete(prompt, json=json)
        path.write_text(
            _json_mod.dumps({"prompt_sha1": path.stem, "response": response}),
            encoding="utf-8",
        )
        return response


def _make_fake_llm() -> LLMClient:
    return FakeLLM(
        default_response=ABSTAIN_ANSWER,
    )


def _build_systems(system_names: list[str], llm: LLMClient) -> dict[str, Any]:
    systems: dict[str, Any] = {}
    for name in system_names:
        if name == "baseline":
            systems["baseline"] = BaselineSystem(llm)
        elif name == "rag":
            systems["rag"] = RAGSystem(llm, embedder=HashEmbedder(), k=5)
        elif name == "anchor":
            try:
                from benchmark.systems.anchor import AnchorSystem
                from nova.extraction.extractor import MemoryExtractor
                from nova.pipeline import Anchor
                from nova.retrieval.hybrid import HybridRetriever
                from nova.store.sqlite_store import SqliteMemoryStore

                store = SqliteMemoryStore(":memory:")
                embedder = HashEmbedder()
                extractor = MemoryExtractor(llm=llm)
                retriever = HybridRetriever(store=store, embedder=embedder)
                anchor = Anchor(store=store, extractor=extractor, retriever=retriever)
                systems["anchor"] = AnchorSystem(anchor)
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] anchor system skipped: {exc}", file=sys.stderr)
        else:
            print(f"[warn] unknown system: {name}", file=sys.stderr)
    return systems


def _filter_cases(cases: list[Case], split: str | None) -> list[Case]:
    if split is None:
        return cases
    wanted = Split.DEV if split == "dev" else Split.TEST
    return [c for c in cases if c.split == wanted]


def _run_case(system: Any, case: Case) -> Result:
    return system.run(case)


def _case_row(
    case: Case,
    system_name: str,
    result: Result,
    expected_correct: bool,
) -> dict[str, str]:
    return {
        "case_id": case.id,
        "scenario": case.scenario.value,
        "split": case.split.value,
        "context_dropped": str(case.context_dropped),
        "system": system_name,
        "expected_action": str(case.expected.action),
        "got_action": str(result.action),
        "expected_key_fact": case.expected.key_fact or "",
        "answer": result.answer,
        "correct": str(expected_correct),
        "retrieved_ids": ";".join(result.retrieved_ids),
        "latency_ms": f"{result.latency_ms:.2f}",
        "prompt_tokens": str(result.prompt_tokens),
        "completion_tokens": str(result.completion_tokens),
    }


def run_benchmark(
    seed: int = 7,
    n: int = 150,
    split: str | None = None,
    system_names: list[str] | None = None,
    llm_mode: str = "fake",
    limit: int | None = None,
    cases_dir: Path | None = None,
    results_root: Path | None = None,
    run_id: str | None = None,
) -> Path:
    """Execute benchmark run and write results to disk."""
    if system_names is None:
        system_names = ["baseline", "rag"]

    llm: LLMClient
    if llm_mode == "fake":
        llm = _make_fake_llm()
    else:
        llm = CachingLLM(_make_fake_llm())

    llm = CachingLLM(llm, cache_dir=CACHE_DIR)

    systems = _build_systems(system_names, llm)
    if not systems:
        raise ValueError("No valid systems configured")

    cases_output_dir = cases_dir or Path("benchmark/cases")
    cases = generate(seed=seed, n=n, output_dir=cases_output_dir)
    cases = _filter_cases(cases, split)

    if limit is not None:
        cases = cases[:limit]

    run_id = run_id or str(uuid.uuid4())[:8]
    results_base = results_root or RESULTS_DIR
    run_dir = results_base / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict[str, str]] = []
    pairs_by_system: dict[str, list[tuple[Case, Result]]] = {name: [] for name in systems}

    for case_idx, case in enumerate(cases):
        for sys_name, system in systems.items():
            try:
                result = _run_case(system, case)
            except Exception as exc:  # noqa: BLE001
                print(f"[error] case {case.id} system {sys_name}: {exc}", file=sys.stderr)
                result = Result(
                    answer="",
                    action="abstain",
                    retrieved_ids=[],
                    latency_ms=0.0,
                )
            pairs_by_system[sys_name].append((case, result))

            from benchmark.metrics import check_correctness

            correct = check_correctness(case, result)
            row = _case_row(case, sys_name, result, correct)
            all_rows.append(row)

        if (case_idx + 1) % 10 == 0:
            print(f"  [{case_idx + 1}/{len(cases)}] cases processed", file=sys.stderr)

    csv_path = run_dir / "results.csv"
    if all_rows:
        fieldnames = list(all_rows[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_rows)

    metrics_by_system: dict[str, Any] = {}
    for sys_name, pairs in pairs_by_system.items():
        metrics_by_system[sys_name] = compute_metrics(pairs)

    write_report(
        run_dir=run_dir,
        systems=list(systems.keys()),
        pairs_by_system=pairs_by_system,
        metrics_by_system=metrics_by_system,
        seed=seed,
        n=n,
        split=split,
        llm_mode=llm_mode,
        limit=limit,
    )

    return run_dir


def main() -> None:
    """Entry point for CLI benchmark runner."""
    parser = argparse.ArgumentParser(description="Nova Context Anchor benchmark runner")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--n", type=int, default=150)
    parser.add_argument("--split", choices=["dev", "test"], default=None)
    parser.add_argument("--systems", default="baseline,rag")
    parser.add_argument("--llm", choices=["fake", "real"], default="fake", dest="llm_mode")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    system_names = [s.strip() for s in args.systems.split(",") if s.strip()]

    t0 = time.perf_counter()
    run_dir = run_benchmark(
        seed=args.seed,
        n=args.n,
        split=args.split,
        system_names=system_names,
        llm_mode=args.llm_mode,
        limit=args.limit,
    )
    elapsed = time.perf_counter() - t0

    print(f"\nRun complete in {elapsed:.1f}s → {run_dir}")
    summary = run_dir / "summary.md"
    if summary.exists():
        print(summary.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
