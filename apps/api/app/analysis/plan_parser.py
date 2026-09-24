"""
PostgreSQL EXPLAIN plan parser.
Converts the raw JSONB plan (from EXPLAIN (FORMAT JSON, ANALYZE)) into
structured signal dictionaries that drive candidate generation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlanNode:
    node_type: str
    relation_name: str | None = None
    alias: str | None = None
    schema: str | None = None
    startup_cost: float = 0.0
    total_cost: float = 0.0
    plan_rows: int = 0
    actual_rows: int | None = None
    actual_total_time: float | None = None
    filter: str | None = None
    index_cond: str | None = None
    recheck_cond: str | None = None
    hash_cond: str | None = None
    join_filter: str | None = None
    sort_key: list[str] = field(default_factory=list)
    group_key: list[str] = field(default_factory=list)
    children: list["PlanNode"] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


def parse_plan(plan_json: list[dict] | dict) -> PlanNode:
    """
    Parse a PostgreSQL EXPLAIN JSON into a PlanNode tree.
    Accepts both the full EXPLAIN output (list) and the inner plan dict.
    """
    if isinstance(plan_json, list):
        plan_json = plan_json[0]
    # The outer dict has "Plan" key
    raw_node = plan_json.get("Plan", plan_json)
    return _parse_node(raw_node)


def _parse_node(raw: dict) -> PlanNode:
    node = PlanNode(
        node_type=raw.get("Node Type", "Unknown"),
        relation_name=raw.get("Relation Name"),
        alias=raw.get("Alias"),
        schema=raw.get("Schema"),
        startup_cost=raw.get("Startup Cost", 0.0),
        total_cost=raw.get("Total Cost", 0.0),
        plan_rows=raw.get("Plan Rows", 0),
        actual_rows=raw.get("Actual Rows"),
        actual_total_time=raw.get("Actual Total Time"),
        filter=raw.get("Filter"),
        index_cond=raw.get("Index Cond"),
        recheck_cond=raw.get("Recheck Cond"),
        hash_cond=raw.get("Hash Cond"),
        join_filter=raw.get("Join Filter"),
        sort_key=raw.get("Sort Key", []),
        group_key=raw.get("Group Key", []),
        raw=raw,
    )
    for child_raw in raw.get("Plans", []):
        node.children.append(_parse_node(child_raw))
    return node


def collect_nodes(root: PlanNode, node_type_fragment: str | None = None) -> list[PlanNode]:
    """Flatten plan tree, optionally filtering by node type substring."""
    results: list[PlanNode] = []

    def _walk(node: PlanNode) -> None:
        if node_type_fragment is None or node_type_fragment.lower() in node.node_type.lower():
            results.append(node)
        for child in node.children:
            _walk(child)

    _walk(root)
    return results


def extract_plan_signals(plan_json: Any) -> dict:
    """
    Extract structured signals from a plan for storage in plan_signals JSONB
    and for downstream candidate generation.

    Returns a dict with:
      - seq_scans: [{table, filter, rows}]
      - sort_nodes: [{sort_key, rows}]
      - hash_joins: [{hash_cond, rows}]
      - nested_loops: int
      - total_cost: float
      - plan_rows: int
      - has_index_scan: bool
      - has_seq_scan: bool
    """
    if not plan_json:
        return {}

    try:
        root = parse_plan(plan_json)
    except Exception:
        return {}

    seq_scans = []
    for node in collect_nodes(root, "Seq Scan"):
        seq_scans.append({
            "table": node.relation_name,
            "filter": node.filter,
            "rows": node.plan_rows,
        })

    sort_nodes = []
    for node in collect_nodes(root, "Sort"):
        sort_nodes.append({
            "sort_key": node.sort_key,
            "rows": node.plan_rows,
        })

    hash_joins = []
    for node in collect_nodes(root, "Hash Join"):
        hash_joins.append({
            "hash_cond": node.hash_cond,
            "rows": node.plan_rows,
        })

    index_scans = collect_nodes(root, "Index") + collect_nodes(root, "Bitmap")
    nested_loops = collect_nodes(root, "Nested Loop")

    return {
        "seq_scans": seq_scans,
        "sort_nodes": sort_nodes,
        "hash_joins": hash_joins,
        "nested_loops": len(nested_loops),
        "total_cost": root.total_cost,
        "plan_rows": root.plan_rows,
        "has_index_scan": len(index_scans) > 0,
        "has_seq_scan": len(seq_scans) > 0,
    }
