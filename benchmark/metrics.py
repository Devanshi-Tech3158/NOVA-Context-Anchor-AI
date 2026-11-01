"""Deterministic benchmark metrics calculation with bootstrap confidence intervals."""

from collections.abc import Callable
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from benchmark.schema import Case, Scenario
from benchmark.systems.base import Result
from nova.core.config import get_settings
from nova.core.schemas import DecisionAction

PRICE_TABLE_PER_MILLION: dict[str, dict[str, float]] = {
    "fake": {"prompt": 0.0, "completion": 0.0},
    "fake-model": {"prompt": 0.0, "completion": 0.0},
    "claude-3-5-sonnet-20241022": {"prompt": 3.0, "completion": 15.0},
    "gpt-4o": {"prompt": 2.5, "completion": 10.0},
    "gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
}


def normalize_text(text: str) -> str:
    """Normalize text by converting to lowercase and collapsing consecutive whitespace."""
    return " ".join(text.lower().split())


def normalize_action(action: DecisionAction | str) -> str:
    """Normalize action enum or string to lowercase value without enum prefixes."""
    val = action.value if hasattr(action, "value") else str(action)
    return val.lower().replace("decisionaction.", "")


def check_correctness(case: Case, result: Result) -> bool:
    """Check if normalized key_fact is a substring of the normalized answer."""
    if case.expected.key_fact is None:
        return False
    norm_fact = normalize_text(case.expected.key_fact)
    norm_ans = normalize_text(result.answer)
    return norm_fact in norm_ans


class MetricScore(BaseModel):
    """Metric value along with its 95% bootstrap confidence interval."""

    value: float | None
    ci_low: float | None = None
    ci_high: float | None = None

    def __getitem__(self, item: str) -> Any:
        """Allow dictionary-style access to score fields."""
        return getattr(self, item)


def compute_recall(pairs: list[tuple[Case, Result]]) -> float | None:
    """Compute correctness over buried_fact, paraphrased, and cross_session cases."""
    subset = [
        p
        for p in pairs
        if p[0].scenario in (Scenario.BURIED_FACT, Scenario.PARAPHRASED, Scenario.CROSS_SESSION)
    ]
    if not subset:
        return None
    return sum(1 for c, r in subset if check_correctness(c, r)) / len(subset)


def compute_accuracy_after_context_loss(pairs: list[tuple[Case, Result]]) -> float | None:
    """Compute correctness on cases where context_dropped is true."""
    subset = [p for p in pairs if p[0].context_dropped is True]
    if not subset:
        return None
    return sum(1 for c, r in subset if check_correctness(c, r)) / len(subset)


def compute_contradiction_precision(pairs: list[tuple[Case, Result]]) -> float | None:
    """Compute precision of contradiction detection across all cases."""
    pred_pos = [p for p in pairs if normalize_action(p[1].action) in ("flag_conflict", "correct")]
    if not pred_pos:
        return None
    tp = sum(1 for c, _ in pred_pos if c.scenario == Scenario.CONTRADICTING_DRAFT)
    return tp / len(pred_pos)


def compute_contradiction_recall(pairs: list[tuple[Case, Result]]) -> float | None:
    """Compute recall of contradiction detection on contradicting_draft cases."""
    act_pos = [p for p in pairs if p[0].scenario == Scenario.CONTRADICTING_DRAFT]
    if not act_pos:
        return None
    tp = sum(1 for _, r in act_pos if normalize_action(r.action) in ("flag_conflict", "correct"))
    return tp / len(act_pos)


def compute_unsupported_claim_rate(pairs: list[tuple[Case, Result]]) -> float | None:
    """Compute share of unanswerable cases where system did not abstain."""
    unans = [p for p in pairs if p[0].scenario == Scenario.UNANSWERABLE]
    if not unans:
        return None
    not_abstained = sum(1 for _, r in unans if normalize_action(r.action) != "abstain")
    return not_abstained / len(unans)


def compute_correct_abstention(pairs: list[tuple[Case, Result]]) -> float | None:
    """Compute share of unanswerable cases where system correctly abstained."""
    unans = [p for p in pairs if p[0].scenario == Scenario.UNANSWERABLE]
    if not unans:
        return None
    abstained = sum(1 for _, r in unans if normalize_action(r.action) == "abstain")
    return abstained / len(unans)


def compute_retrieval_accuracy(pairs: list[tuple[Case, Result]]) -> float | None:
    """Compute share of cases where expected source message id is in retrieved_ids."""
    eligible = [p for p in pairs if p[0].expected.source_msg_id is not None]
    if not eligible:
        return None
    hits = sum(1 for c, r in eligible if c.expected.source_msg_id in r.retrieved_ids)
    return hits / len(eligible)


def compute_false_warning_rate(pairs: list[tuple[Case, Result]]) -> float | None:
    """Compute share of valid_answer cases where action was not answer."""
    valid_cases = [p for p in pairs if p[0].scenario == Scenario.VALID_ANSWER]
    if not valid_cases:
        return None
    warned = sum(1 for _, r in valid_cases if normalize_action(r.action) != "answer")
    return warned / len(valid_cases)


def bootstrap_ci(
    data: list[tuple[Case, Result]],
    metric_fn: Callable[[list[tuple[Case, Result]]], float | None],
    resamples: int = 1000,
    seed: int = 42,
    alpha: float = 0.05,
) -> tuple[float, float] | None:
    """Compute bootstrap 95% confidence interval using fixed seed resampling."""
    point_est = metric_fn(data)
    if point_est is None or not data:
        return None

    n = len(data)
    rng = np.random.default_rng(seed)
    boot_indices = rng.integers(0, n, size=(resamples, n))

    boot_values: list[float] = []
    for b in range(resamples):
        sample = [data[idx] for idx in boot_indices[b]]
        val = metric_fn(sample)
        if val is not None:
            boot_values.append(val)

    if not boot_values:
        return None

    low_pct = 100.0 * (alpha / 2.0)
    high_pct = 100.0 * (1.0 - alpha / 2.0)
    ci_low = float(np.percentile(boot_values, low_pct))
    ci_high = float(np.percentile(boot_values, high_pct))
    return (ci_low, ci_high)


def compute_latencies(results: list[Result]) -> tuple[float | None, float | None]:
    """Compute p50 and p95 latencies across results."""
    if not results:
        return None, None
    lats = [r.latency_ms for r in results]
    p50 = float(np.percentile(lats, 50))
    p95 = float(np.percentile(lats, 95))
    return p50, p95


def compute_cost(
    prompt_tokens: int,
    completion_tokens: int,
    model_name: str | None = None,
    rates: dict[str, float] | None = None,
) -> float:
    """Compute estimated USD cost based on token counts and price table."""
    if rates is None:
        settings = get_settings()
        m_name = model_name or settings.llm_model
        rates = PRICE_TABLE_PER_MILLION.get(m_name, {"prompt": 0.0, "completion": 0.0})

    p_cost = (prompt_tokens / 1_000_000.0) * rates.get("prompt", 0.0)
    c_cost = (completion_tokens / 1_000_000.0) * rates.get("completion", 0.0)
    return p_cost + c_cost


class BenchmarkMetrics(BaseModel):
    """Complete suite of benchmark metrics with confidence intervals."""

    recall: MetricScore
    accuracy_after_context_loss: MetricScore
    contradiction_precision: MetricScore
    contradiction_recall: MetricScore
    unsupported_claim_rate: MetricScore
    correct_abstention: MetricScore
    retrieval_accuracy: MetricScore
    false_warning_rate: MetricScore
    latency_p50: float | None = None
    latency_p95: float | None = None
    prompt_tokens_per_case: float | None = None
    completion_tokens_per_case: float | None = None
    total_tokens_per_case: float | None = None
    total_cost: float | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    def __getitem__(self, item: str) -> Any:
        """Allow dictionary-style access to metrics."""
        return getattr(self, item)


def compute_metrics(
    pairs: list[tuple[Case, Result]],
    model_name: str | None = None,
    price_table: dict[str, float] | None = None,
    seed: int = 42,
    resamples: int = 1000,
) -> BenchmarkMetrics:
    """Evaluate full set of benchmark metrics with bootstrap confidence intervals."""
    metric_funcs: dict[str, Callable[[list[tuple[Case, Result]]], float | None]] = {
        "recall": compute_recall,
        "accuracy_after_context_loss": compute_accuracy_after_context_loss,
        "contradiction_precision": compute_contradiction_precision,
        "contradiction_recall": compute_contradiction_recall,
        "unsupported_claim_rate": compute_unsupported_claim_rate,
        "correct_abstention": compute_correct_abstention,
        "retrieval_accuracy": compute_retrieval_accuracy,
        "false_warning_rate": compute_false_warning_rate,
    }

    scores: dict[str, MetricScore] = {}
    for name, fn in metric_funcs.items():
        val = fn(pairs)
        if val is None:
            scores[name] = MetricScore(value=None, ci_low=None, ci_high=None)
        else:
            ci = bootstrap_ci(pairs, fn, resamples=resamples, seed=seed)
            ci_low, ci_high = ci if ci is not None else (val, val)
            scores[name] = MetricScore(value=val, ci_low=ci_low, ci_high=ci_high)

    results = [r for _, r in pairs]
    p50, p95 = compute_latencies(results)

    n = len(results)
    total_p = sum(r.prompt_tokens for r in results)
    total_c = sum(r.completion_tokens for r in results)

    prompt_per_case = (total_p / n) if n else None
    comp_per_case = (total_c / n) if n else None
    tot_per_case = ((total_p + total_c) / n) if n else None

    total_cost = compute_cost(total_p, total_c, model_name=model_name, rates=price_table)

    return BenchmarkMetrics(
        recall=scores["recall"],
        accuracy_after_context_loss=scores["accuracy_after_context_loss"],
        contradiction_precision=scores["contradiction_precision"],
        contradiction_recall=scores["contradiction_recall"],
        unsupported_claim_rate=scores["unsupported_claim_rate"],
        correct_abstention=scores["correct_abstention"],
        retrieval_accuracy=scores["retrieval_accuracy"],
        false_warning_rate=scores["false_warning_rate"],
        latency_p50=p50,
        latency_p95=p95,
        prompt_tokens_per_case=prompt_per_case,
        completion_tokens_per_case=comp_per_case,
        total_tokens_per_case=tot_per_case,
        total_cost=total_cost,
    )
