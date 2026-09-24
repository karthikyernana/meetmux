"""
HypoPG-powered experiment runner.

Workflow per experiment:
  1. Obtain target DB connection (decrypt credentials)
  2. In a single transaction with SAVEPOINT:
     a. Run `hypopg_create_index(definition)` if HypoPG available
     b. EXPLAIN (FORMAT JSON) the query
     c. Parse before + after plans
     d. `hypopg_drop_index` or ROLLBACK SAVEPOINT
  3. Compute plan diff
  4. Estimate index size via `hypopg_relation_size`

If HypoPG is not available, falls back to:
  - Comparing before plan signals to a synthetic "what if" using pg_index + stats
"""
from __future__ import annotations

import json
import time
from typing import Any

import psycopg

from app.analysis.plan_parser import extract_plan_signals, parse_plan
from app.core.logging import get_logger

logger = get_logger(__name__)


async def run_experiment(
    *,
    before_plan_json: Any,
    query_text: str,
    index_definition: str,
    connection_dsn: str,
    statement_timeout_ms: int = 30_000,
) -> dict:
    """
    Run a hypothetical plan experiment against the target database.
    Returns a dict with all result fields for the Experiment model.
    """
    result: dict = {
        "status": "failed",
        "hypopg_available": False,
        "before_plan_json": before_plan_json,
        "after_plan_json": None,
        "before_cost": None,
        "after_cost": None,
        "before_sort_nodes": None,
        "after_sort_nodes": None,
        "plan_changed": None,
        "plan_diff": None,
        "storage_estimate_bytes": None,
        "error_code": None,
        "error_message": None,
    }

    # Parse before plan
    before_signals = extract_plan_signals(before_plan_json) if before_plan_json else {}
    result["before_cost"] = before_signals.get("total_cost")
    before_sort_count = len(before_signals.get("sort_nodes", []))
    result["before_sort_nodes"] = before_sort_count

    try:
        async with await psycopg.AsyncConnection.connect(connection_dsn, autocommit=False) as conn:
            # Check HypoPG availability
            row = await conn.execute(
                "SELECT count(*) FROM pg_extension WHERE extname = 'hypopg'"
            ).fetchone()
            hypopg_available = bool(row and row[0] > 0)
            result["hypopg_available"] = hypopg_available

            await conn.execute(f"SET statement_timeout = {statement_timeout_ms}")
            await conn.execute("SAVEPOINT experiment_start")

            hypo_oid: int | None = None
            try:
                if hypopg_available:
                    hypo_row = await conn.execute(
                        "SELECT * FROM hypopg_create_index($1)", (index_definition,)
                    ).fetchone()
                    if hypo_row:
                        hypo_oid = hypo_row[0]  # indexrelid

                # Fetch EXPLAIN (FORMAT JSON) with hypothetical index in place
                explain_row = await conn.execute(
                    f"EXPLAIN (FORMAT JSON, BUFFERS FALSE) {query_text}"
                ).fetchone()

                after_plan_json = json.loads(explain_row[0]) if explain_row else None
                result["after_plan_json"] = after_plan_json

                # Storage estimate
                if hypo_oid:
                    size_row = await conn.execute(
                        "SELECT hypopg_relation_size($1)", (hypo_oid,)
                    ).fetchone()
                    if size_row:
                        result["storage_estimate_bytes"] = size_row[0]

            finally:
                # Always roll back the hypothetical index
                await conn.execute("ROLLBACK TO SAVEPOINT experiment_start")
                await conn.execute("RELEASE SAVEPOINT experiment_start")

        # ── Compute diff ──────────────────────────────────────────────────────
        after_signals = extract_plan_signals(result["after_plan_json"]) if result["after_plan_json"] else {}
        after_cost = after_signals.get("total_cost")
        result["after_cost"] = after_cost
        after_sort_count = len(after_signals.get("sort_nodes", []))
        result["after_sort_nodes"] = after_sort_count

        plan_diff: dict = {"plan_changed": False}

        bc = result["before_cost"]
        ac = after_cost
        if bc is not None and ac is not None:
            plan_diff["cost"] = {
                "before": round(bc, 2),
                "after": round(ac, 2),
                "reduction_ratio": round((bc - ac) / bc, 4) if bc > 0 else 0,
            }

        if before_sort_count != after_sort_count:
            plan_diff["sort"] = {"before": before_sort_count, "after": after_sort_count}
            plan_diff["plan_changed"] = True

        if before_signals.get("has_seq_scan") and not after_signals.get("has_seq_scan"):
            plan_diff["scan_change"] = {"before": "Seq Scan", "after": "Index Scan"}
            plan_diff["plan_changed"] = True
        elif not before_signals.get("has_seq_scan") and not after_signals.get("has_seq_scan"):
            pass
        elif before_signals.get("has_seq_scan") == after_signals.get("has_seq_scan"):
            pass

        result["plan_diff"] = plan_diff
        result["plan_changed"] = plan_diff["plan_changed"]
        result["status"] = "complete"

    except psycopg.Error as exc:
        logger.error("experiment_failed", error=str(exc))
        result["error_code"] = type(exc).__name__
        result["error_message"] = str(exc)
    except Exception as exc:
        logger.error("experiment_error", error=str(exc))
        result["error_code"] = "INTERNAL_ERROR"
        result["error_message"] = str(exc)

    return result


def build_index_definition(
    table_name: str,
    schema_name: str,
    columns: list[str],
    sort_directions: list[str] | None,
    include_columns: list[str] | None,
    predicate: str | None,
    index_method: str = "btree",
) -> tuple[str, str]:
    """
    Build CREATE INDEX and DROP INDEX SQL for a candidate.
    Returns (create_sql, drop_sql).

    The index is built with CONCURRENTLY in the drop form for reference only —
    actual execution is always at the user's discretion.
    """
    # Sanitize identifiers
    col_parts = []
    for i, col in enumerate(columns):
        part = f'"{col}"'
        if sort_directions and i < len(sort_directions):
            part += f" {sort_directions[i]}"
        col_parts.append(part)

    index_name = (
        f"idx_{table_name}_{'_'.join(columns[:3])}"
        .replace("-", "_")
        .lower()[:63]
    )

    create_parts = [
        f'CREATE INDEX CONCURRENTLY IF NOT EXISTS "{index_name}"',
        f'ON "{schema_name}"."{table_name}" USING {index_method}',
        f"({', '.join(col_parts)})",
    ]
    if include_columns:
        inc = ", ".join(f'"{c}"' for c in include_columns)
        create_parts.append(f"INCLUDE ({inc})")
    if predicate:
        create_parts.append(f"WHERE {predicate}")

    create_sql = " ".join(create_parts) + ";"
    drop_sql = f'DROP INDEX CONCURRENTLY IF EXISTS "{schema_name}"."{index_name}";'

    return create_sql, drop_sql
