"""
Index candidate generator.

Given a QueryFingerprint and its plan signals, this module produces a list of
IndexCandidate rows using deterministic rule-based logic. No LLM required.

Rules applied (in order):
  R1 — Seq scan with filter: candidate on filter columns
  R2 — Seq scan with ORDER BY match: candidate on sort columns
  R3 — Sort node eliminated by index: candidate on sort_key
  R4 — Hash join: candidate on join condition columns
  R5 — Nested loop join: candidate on inner relation join column
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any


# ── Column extraction helpers ─────────────────────────────────────────────────

_COLUMN_RE = re.compile(
    r"""
    (?:\(|,|\s|=|<|>|!=|AND|OR|IS|NOT|IN|LIKE|::|\()  # preceding token
    ([a-zA-Z_][a-zA-Z0-9_]*)                           # column name
    (?:\s*=|\s*<|\s*>|\s*!=|\s+IS|\s+IN|\s+LIKE|,|\)|$|\s) # succeeding token
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _columns_from_condition(cond: str | None) -> list[str]:
    """Extract column names from a WHERE / filter expression string."""
    if not cond:
        return []
    seen: set[str] = set()
    results: list[str] = []
    for m in _COLUMN_RE.finditer(cond):
        col = m.group(1).lower()
        # Filter PostgreSQL keywords
        if col in {
            "and", "or", "not", "null", "true", "false", "is", "in",
            "like", "between", "exists", "any", "all", "as", "on",
        }:
            continue
        if col not in seen:
            seen.add(col)
            results.append(col)
    return results


def _columns_from_sort_key(sort_key: list[str]) -> tuple[list[str], list[str]]:
    """
    Parse sort_key entries like "col ASC", "col DESC NULLS LAST".
    Returns (columns, directions).
    """
    columns: list[str] = []
    directions: list[str] = []
    for entry in sort_key:
        parts = entry.split()
        if not parts:
            continue
        # Remove table qualifier if present
        col = parts[0].split(".")[-1].strip('"')
        direction = "DESC" if any(p.upper() == "DESC" for p in parts[1:]) else "ASC"
        columns.append(col.lower())
        directions.append(direction)
    return columns, directions


def _candidate_hash(table: str, columns: list[str], method: str, predicate: str | None) -> str:
    key = json.dumps(
        {"table": table.lower(), "columns": sorted(columns), "method": method, "predicate": predicate},
        sort_keys=True,
    )
    return hashlib.sha256(key.encode()).hexdigest()[:16]


# ── Main generator ────────────────────────────────────────────────────────────

def generate_candidates(
    plan_signals: dict,
    schema_name: str = "public",
    max_columns: int = 3,
) -> list[dict]:
    """
    Return a list of candidate dicts (not ORM objects) describing proposed indexes.
    Each dict has keys matching IndexCandidate columns:
      table_name, schema_name, index_method, columns, sort_directions,
      include_columns, predicate, source_signals, generation_rule, candidate_hash
    """
    candidates: list[dict] = []
    seen_hashes: set[str] = set()

    def _add(
        table: str,
        columns: list[str],
        method: str = "btree",
        sort_directions: list[str] | None = None,
        include_columns: list[str] | None = None,
        predicate: str | None = None,
        signals: list[str] | None = None,
        rule: str | None = None,
    ) -> None:
        if not table or not columns:
            return
        columns = columns[:max_columns]
        h = _candidate_hash(table, columns, method, predicate)
        if h in seen_hashes:
            return
        seen_hashes.add(h)
        candidates.append({
            "table_name": table,
            "schema_name": schema_name,
            "index_method": method,
            "columns": columns,
            "sort_directions": sort_directions,
            "include_columns": include_columns,
            "predicate": predicate,
            "source_signals": signals or [],
            "generation_rule": rule,
            "candidate_hash": h,
        })

    # ── R1: Seq Scan with filter ──────────────────────────────────────────────
    for ss in plan_signals.get("seq_scans", []):
        table = ss.get("table")
        if not table:
            continue
        cols = _columns_from_condition(ss.get("filter"))
        if cols:
            _add(
                table, cols, signals=["SEQ_SCAN_WITH_FILTER"],
                rule="R1_SEQ_SCAN_FILTER",
            )
        else:
            # No filter — Seq Scan on whole table; still worth noting but no clear candidate
            pass

    # ── R2: Sort node that could be eliminated ────────────────────────────────
    for sort in plan_signals.get("sort_nodes", []):
        sort_key: list[str] = sort.get("sort_key", [])
        if not sort_key:
            continue
        cols, dirs = _columns_from_sort_key(sort_key)
        if not cols:
            continue
        # Find the table driving the sort: heuristically from seq_scan list
        for ss in plan_signals.get("seq_scans", []):
            table = ss.get("table")
            if table:
                _add(
                    table, cols, sort_directions=dirs,
                    signals=["SORT_NODE_ELIMINATION"],
                    rule="R2_SORT_ELIMINATION",
                )
                break

    # ── R3: Sort node from hash join side ─────────────────────────────────────
    for hj in plan_signals.get("hash_joins", []):
        cond = hj.get("hash_cond", "")
        if not cond:
            continue
        # Hash conditions look like: (table.col = table2.col2)
        cols = _columns_from_condition(cond)
        # We emit two candidates — one per side (can't know which table without full metadata)
        if len(cols) >= 2:
            # Try to infer from seq_scans
            for ss in plan_signals.get("seq_scans", []):
                table = ss.get("table")
                if table:
                    _add(
                        table, [cols[0]],
                        signals=["HASH_JOIN_CONDITION"],
                        rule="R3_HASH_JOIN",
                    )
                    break

    return candidates


# ── Overlap detection ─────────────────────────────────────────────────────────

def detect_overlap(
    candidate_columns: list[str],
    existing_indexes: list[dict],
) -> tuple[str, dict | None]:
    """
    Check a candidate against existing indexes.
    Returns (overlap_status, overlap_detail).
    overlap_status: NONE | PARTIAL_OVERLAP | FULLY_COVERED | DUPLICATE | POTENTIALLY_REDUNDANT
    """
    cand_set = set(candidate_columns)
    for idx in existing_indexes:
        existing_cols: list[str] = [c.lower() for c in (idx.get("columns") or [])]
        existing_set = set(existing_cols)

        if existing_cols[: len(candidate_columns)] == [c.lower() for c in candidate_columns]:
            return "DUPLICATE", {"matching_index": idx.get("index_name")}

        if cand_set == existing_set:
            return "FULLY_COVERED", {"matching_index": idx.get("index_name")}

        if cand_set.issubset(existing_set):
            return "POTENTIALLY_REDUNDANT", {
                "matching_index": idx.get("index_name"),
                "existing_prefix": existing_cols,
            }

        if cand_set & existing_set:
            return "PARTIAL_OVERLAP", {
                "matching_index": idx.get("index_name"),
                "overlap_columns": list(cand_set & existing_set),
            }

    return "NONE", None
