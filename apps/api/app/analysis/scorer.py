"""
Scoring engine for index recommendations.

Deterministic scoring — PostgreSQL is the authority, not the LLM.

Score components (all normalized to [0, 1]):
  benefit_score   — based on cost reduction, plan change, sort removal
  storage_penalty — based on estimated index size vs relation size
  write_penalty   — based on n_tup_ins + n_tup_upd + n_tup_del
  overlap_penalty — based on overlap_status

Final score = benefit_score − storage_penalty − write_penalty − overlap_penalty

Thresholds → status:
  score >= 0.60                        → RECOMMENDED
  0.40 <= score < 0.60                 → REVIEW_REQUIRED
  cost_reduction is None or < 0.10    → INCONCLUSIVE
  overlap_status in {DUPLICATE, ...}   → REJECTED
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


RECOMMENDATION_THRESHOLD = 0.60
REVIEW_THRESHOLD = 0.40
MINIMUM_BENEFIT = 0.10   # cost_reduction must exceed this to avoid INCONCLUSIVE


@dataclass
class ScoringInput:
    # Experiment results
    before_cost: float | None = None
    after_cost: float | None = None
    before_sort_nodes: int | None = None
    after_sort_nodes: int | None = None
    plan_changed: bool | None = None
    storage_estimate_bytes: int | None = None
    hypopg_available: bool = False
    # Stats from pg_stat_user_tables (optional)
    n_tup_ins: int | None = None
    n_tup_upd: int | None = None
    n_tup_del: int | None = None
    relpages: int | None = None
    # Workload
    calls: int | None = None
    total_exec_time: float | None = None
    # Overlap
    overlap_status: str = "NONE"


@dataclass
class ScoringResult:
    status: str
    score: float
    benefit_score: float
    storage_penalty: float
    write_penalty: float
    overlap_penalty: float
    evidence_quality: str
    reason_codes: list[str]
    jev_review_path: str | None = None


def score_candidate(inp: ScoringInput) -> ScoringResult:
    reason_codes: list[str] = []

    # ── Immediate REJECTED conditions ─────────────────────────────────────────
    if inp.overlap_status in ("DUPLICATE", "FULLY_COVERED"):
        reason_codes.append(f"EXISTING_INDEX_OVERLAP_{inp.overlap_status}")
        return ScoringResult(
            status="REJECTED",
            score=0.0,
            benefit_score=0.0,
            storage_penalty=0.0,
            write_penalty=0.0,
            overlap_penalty=1.0,
            evidence_quality="HIGH",
            reason_codes=reason_codes,
        )

    # ── Cost reduction benefit ────────────────────────────────────────────────
    cost_reduction_ratio: float | None = None
    if inp.before_cost and inp.after_cost and inp.before_cost > 0:
        cost_reduction_ratio = (inp.before_cost - inp.after_cost) / inp.before_cost
        if cost_reduction_ratio > 0:
            reason_codes.append("PLAN_COST_REDUCTION")
        benefit_score = min(cost_reduction_ratio, 1.0)
    else:
        benefit_score = 0.0

    # Sort elimination bonus (+0.15)
    sort_bonus = 0.0
    if (inp.before_sort_nodes is not None and inp.after_sort_nodes is not None
            and inp.after_sort_nodes < inp.before_sort_nodes):
        sort_bonus = 0.15
        reason_codes.append("SORT_REMOVED")

    benefit_score = min(benefit_score + sort_bonus, 1.0)

    # Plan changed at all?
    if inp.plan_changed:
        reason_codes.append("PLAN_CHANGED")

    # Confidence downgrade if HypoPG unavailable
    if not inp.hypopg_available:
        benefit_score *= 0.6
        reason_codes.append("HYPOPG_UNAVAILABLE")

    # ── Storage penalty ───────────────────────────────────────────────────────
    storage_penalty = 0.0
    if inp.storage_estimate_bytes:
        gb = inp.storage_estimate_bytes / (1024 ** 3)
        if gb > 10:
            storage_penalty = 0.30
            reason_codes.append("HIGH_STORAGE_COST")
        elif gb > 1:
            storage_penalty = 0.10

    # ── Write penalty ─────────────────────────────────────────────────────────
    write_penalty = 0.0
    writes = (inp.n_tup_ins or 0) + (inp.n_tup_upd or 0) + (inp.n_tup_del or 0)
    reads = inp.calls or 0
    if writes and reads:
        write_ratio = writes / max(reads, 1)
        if write_ratio > 5.0:
            write_penalty = 0.25
            reason_codes.append("HIGH_WRITE_ACTIVITY")
        elif write_ratio > 2.0:
            write_penalty = 0.10

    # ── Overlap penalty ───────────────────────────────────────────────────────
    overlap_penalty = 0.0
    if inp.overlap_status == "PARTIALLY_REDUNDANT":
        overlap_penalty = 0.15
        reason_codes.append("POTENTIALLY_REDUNDANT_INDEX")
    elif inp.overlap_status == "PARTIAL_OVERLAP":
        overlap_penalty = 0.05

    # ── Evidence quality ──────────────────────────────────────────────────────
    if inp.hypopg_available and cost_reduction_ratio is not None:
        evidence_quality = "HIGH"
    elif cost_reduction_ratio is not None:
        evidence_quality = "MEDIUM"
    else:
        evidence_quality = "LOW"
        reason_codes.append("LOW_EVIDENCE")

    # ── Final score ───────────────────────────────────────────────────────────
    score = benefit_score - storage_penalty - write_penalty - overlap_penalty
    score = max(0.0, min(score, 1.0))

    # ── Status determination ──────────────────────────────────────────────────
    if cost_reduction_ratio is None or (cost_reduction_ratio < MINIMUM_BENEFIT and not sort_bonus):
        status = "INCONCLUSIVE"
    elif score >= RECOMMENDATION_THRESHOLD:
        status = "RECOMMENDED"
    elif score >= REVIEW_THRESHOLD:
        status = "REVIEW_REQUIRED"
    else:
        status = "INCONCLUSIVE"

    # ── JEV review path (classification for deeper review) ───────────────────
    jev_review_path: str | None = None
    if status == "REVIEW_REQUIRED":
        if write_penalty > 0.15:
            jev_review_path = "WRITE_HEAVY_TABLE"
        elif storage_penalty > 0.15:
            jev_review_path = "LARGE_INDEX"
        elif overlap_penalty > 0:
            jev_review_path = "OVERLAPPING_INDEX"
        else:
            jev_review_path = "BORDERLINE_BENEFIT"

    return ScoringResult(
        status=status,
        score=round(score, 4),
        benefit_score=round(benefit_score, 4),
        storage_penalty=round(storage_penalty, 4),
        write_penalty=round(write_penalty, 4),
        overlap_penalty=round(overlap_penalty, 4),
        evidence_quality=evidence_quality,
        reason_codes=reason_codes,
        jev_review_path=jev_review_path,
    )


def build_explanation(result: ScoringResult, candidate: dict) -> str:
    """Build a deterministic, template-based explanation for the recommendation."""
    table = candidate.get("table_name", "the table")
    columns = ", ".join(candidate.get("columns", []))
    method = candidate.get("index_method", "btree").upper()

    lines: list[str] = [
        f"Proposed: CREATE INDEX ON {table} ({columns}) USING {method}.",
        "",
    ]

    if result.status == "RECOMMENDED":
        lines.append(
            f"This index is recommended based on {result.evidence_quality.lower()}-confidence "
            f"evidence (score: {result.score:.2f})."
        )
    elif result.status == "REVIEW_REQUIRED":
        lines.append(
            f"Review required before deploying (score: {result.score:.2f}). "
            f"See '{result.jev_review_path}' for the primary concern."
        )
    elif result.status == "INCONCLUSIVE":
        lines.append(
            "Analysis could not determine a clear benefit. The experiment may lack sufficient "
            "data or the plan cost improvement is below the minimum threshold."
        )
    elif result.status == "REJECTED":
        lines.append(
            "This index is redundant. An equivalent or covering index already exists on the table."
        )

    if "PLAN_COST_REDUCTION" in result.reason_codes:
        lines.append(f"• Planner cost reduction: {result.benefit_score * 100:.1f}%.")
    if "SORT_REMOVED" in result.reason_codes:
        lines.append("• A Sort node is eliminated by this index, reducing memory usage.")
    if "HIGH_WRITE_ACTIVITY" in result.reason_codes:
        lines.append("• High write activity on this table will increase maintenance overhead.")
    if "HIGH_STORAGE_COST" in result.reason_codes:
        lines.append("• The estimated index size is large. Evaluate storage capacity before applying.")
    if "HYPOPG_UNAVAILABLE" in result.reason_codes:
        lines.append(
            "• HypoPG was not available; plan estimates are based on existing plan shapes, "
            "not hypothetical indexing. Confidence is reduced."
        )

    return "\n".join(lines)
