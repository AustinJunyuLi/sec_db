"""Cost and runtime envelope helpers for corpus-scale run planning."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal, Mapping

TokenUsageBasis = Literal["actual", "estimated", "mixed"]


@dataclass(frozen=True)
class DealCostRuntimeMetrics:
    deal_slug: str
    windows: int
    input_tokens: int
    output_tokens: int
    claims: int
    coverage_obligations: int
    linkflow_latencies_seconds: tuple[float, ...]
    retry_count: int = 0
    provider_failure_count: int = 0
    quote_validation_rejection_count: int = 0
    disposition_counts: Mapping[str, int] = field(default_factory=dict)
    cost_usd: float | None = None
    token_usage_basis: TokenUsageBasis = "estimated"

    def __post_init__(self) -> None:
        if not self.deal_slug:
            raise ValueError("deal_slug is required")
        for field_name in (
            "windows",
            "input_tokens",
            "output_tokens",
            "claims",
            "coverage_obligations",
            "retry_count",
            "provider_failure_count",
            "quote_validation_rejection_count",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must be non-negative")
        if any(value < 0 for value in self.linkflow_latencies_seconds):
            raise ValueError("linkflow_latencies_seconds must be non-negative")
        if self.token_usage_basis not in {"actual", "estimated", "mixed"}:
            raise ValueError("token_usage_basis must be actual, estimated, or mixed")
        if self.cost_usd is not None and self.cost_usd < 0:
            raise ValueError("cost_usd must be non-negative when provided")


@dataclass(frozen=True)
class CostEnvelopeAssumptions:
    input_cost_per_million_tokens: float
    output_cost_per_million_tokens: float
    latency_projection: str
    retry_projection: str
    rejection_projection: str
    currency: str = "USD"
    projection_deal_counts: tuple[int, ...] = (9, 30, 400, 800)
    scaling_method: str = "linear_from_observed_three_deal_metrics"

    def __post_init__(self) -> None:
        if self.input_cost_per_million_tokens < 0:
            raise ValueError("input_cost_per_million_tokens must be non-negative")
        if self.output_cost_per_million_tokens < 0:
            raise ValueError("output_cost_per_million_tokens must be non-negative")
        for field_name in ("latency_projection", "retry_projection", "rejection_projection"):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} is required")
        if any(count <= 0 for count in self.projection_deal_counts):
            raise ValueError("projection_deal_counts must be positive")


def build_cost_runtime_summary(
    observed_metrics: list[DealCostRuntimeMetrics],
    assumptions: CostEnvelopeAssumptions,
) -> dict[str, object]:
    if len(observed_metrics) != 3:
        raise ValueError("cost/runtime envelope requires exactly three observed deal metrics")
    observed_deal_count = len(observed_metrics)
    observed = _observed_summary(observed_metrics)
    usage_basis = _usage_basis(observed_metrics)
    projection_counts = (observed_deal_count, *assumptions.projection_deal_counts)
    projections = [
        _projection_row(
            deal_count=count,
            observed=observed,
            observed_deal_count=observed_deal_count,
            assumptions=assumptions,
            usage_basis=usage_basis,
        )
        for count in projection_counts
    ]
    return {
        "summary_version": "corpus_cost_runtime_envelope_v1",
        "usage_basis": usage_basis,
        "observed": observed,
        "assumptions": {
            "input_cost_per_million_tokens": assumptions.input_cost_per_million_tokens,
            "output_cost_per_million_tokens": assumptions.output_cost_per_million_tokens,
            "currency": assumptions.currency,
            "scaling_method": assumptions.scaling_method,
            "latency_projection": assumptions.latency_projection,
            "retry_projection": assumptions.retry_projection,
            "rejection_projection": assumptions.rejection_projection,
            "projection_deal_counts": list(assumptions.projection_deal_counts),
        },
        "projections": projections,
    }


def cost_summary_csv_rows(summary: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for projection in summary["projections"]:  # type: ignore[index]
        rows.append(
            {
                "deal_count": projection["deal_count"],
                "cost_basis": projection["cost_basis"],
                "projected_windows": projection["projected_windows"],
                "projected_input_tokens": projection["projected_input_tokens"],
                "projected_output_tokens": projection["projected_output_tokens"],
                "projected_claims": projection["projected_claims"],
                "projected_coverage_obligations": projection["projected_coverage_obligations"],
                "projected_retry_count": projection["projected_retry_count"],
                "projected_provider_failures": projection["projected_provider_failures"],
                "projected_quote_validation_rejections": projection["projected_quote_validation_rejections"],
                "estimated_cost_usd": projection["estimated_cost_usd"],
                "actual_cost_usd": projection["actual_cost_usd"],
                "assumption_basis": projection["assumption_basis"],
            }
        )
    return rows


def _usage_basis(observed_metrics: list[DealCostRuntimeMetrics]) -> TokenUsageBasis:
    bases = {metric.token_usage_basis for metric in observed_metrics}
    if bases == {"actual"}:
        return "actual"
    if bases == {"estimated"}:
        return "estimated"
    return "mixed"


def _observed_summary(observed_metrics: list[DealCostRuntimeMetrics]) -> dict[str, object]:
    latencies = [
        latency
        for metric in observed_metrics
        for latency in metric.linkflow_latencies_seconds
    ]
    disposition_mix: dict[str, int] = {}
    for metric in observed_metrics:
        for disposition, count in metric.disposition_counts.items():
            disposition_mix[disposition] = disposition_mix.get(disposition, 0) + int(count)
    claims = sum(metric.claims for metric in observed_metrics)
    quote_rejections = sum(metric.quote_validation_rejection_count for metric in observed_metrics)
    actual_costs = [metric.cost_usd for metric in observed_metrics if metric.cost_usd is not None]
    deal_count = len(observed_metrics)
    return {
        "deal_count": deal_count,
        "deal_slugs": [metric.deal_slug for metric in observed_metrics],
        "windows": sum(metric.windows for metric in observed_metrics),
        "windows_per_deal": sum(metric.windows for metric in observed_metrics) / deal_count,
        "input_tokens": sum(metric.input_tokens for metric in observed_metrics),
        "input_tokens_per_deal": sum(metric.input_tokens for metric in observed_metrics) / deal_count,
        "output_tokens": sum(metric.output_tokens for metric in observed_metrics),
        "output_tokens_per_deal": sum(metric.output_tokens for metric in observed_metrics) / deal_count,
        "claims": claims,
        "claims_per_deal": claims / deal_count,
        "coverage_obligations": sum(metric.coverage_obligations for metric in observed_metrics),
        "coverage_obligations_per_deal": (
            sum(metric.coverage_obligations for metric in observed_metrics) / deal_count
        ),
        "latency_seconds": {
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "max": max(latencies) if latencies else 0.0,
        },
        "retry_count": sum(metric.retry_count for metric in observed_metrics),
        "provider_failures": sum(metric.provider_failure_count for metric in observed_metrics),
        "quote_validation_rejections": quote_rejections,
        "quote_validation_rejection_rate": quote_rejections / claims if claims else 0.0,
        "disposition_mix": dict(sorted(disposition_mix.items())),
        "actual_cost_usd": sum(actual_costs) if len(actual_costs) == deal_count else None,
        "partial_actual_cost_usd": sum(actual_costs) if actual_costs else None,
    }


def _projection_row(
    *,
    deal_count: int,
    observed: dict[str, object],
    observed_deal_count: int,
    assumptions: CostEnvelopeAssumptions,
    usage_basis: TokenUsageBasis,
) -> dict[str, object]:
    scale = deal_count / observed_deal_count
    projected_input_tokens = float(observed["input_tokens"]) * scale
    projected_output_tokens = float(observed["output_tokens"]) * scale
    estimated_cost = (
        projected_input_tokens * assumptions.input_cost_per_million_tokens
        + projected_output_tokens * assumptions.output_cost_per_million_tokens
    ) / 1_000_000
    actual_cost = observed["actual_cost_usd"] if deal_count == observed_deal_count else None
    return {
        "deal_count": deal_count,
        "cost_basis": usage_basis,
        "projected_windows": float(observed["windows"]) * scale,
        "projected_input_tokens": projected_input_tokens,
        "projected_output_tokens": projected_output_tokens,
        "projected_claims": float(observed["claims"]) * scale,
        "projected_coverage_obligations": float(observed["coverage_obligations"]) * scale,
        "projected_retry_count": float(observed["retry_count"]) * scale,
        "projected_provider_failures": float(observed["provider_failures"]) * scale,
        "projected_quote_validation_rejections": float(observed["quote_validation_rejections"]) * scale,
        "estimated_cost_usd": estimated_cost,
        "actual_cost_usd": actual_cost,
        "assumption_basis": assumptions.scaling_method,
    }


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if percentile == 0.50 and len(ordered) % 2 == 0:
        midpoint = len(ordered) // 2
        return (ordered[midpoint - 1] + ordered[midpoint]) / 2
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]
