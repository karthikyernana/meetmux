import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { RefreshCw, Loader2, ChevronDown, ChevronUp, Activity } from "lucide-react";
import { api } from "@/api/client";
import { formatMs, formatNumber } from "@/lib/utils";

type SortKey = "workload_impact_score" | "calls" | "mean_exec_time" | "total_exec_time";
type SortDir = "asc" | "desc";

const REC_BADGE: Record<string, string> = {
  RECOMMENDED:     "badge badge-ok",
  REVIEW_REQUIRED: "badge badge-warn",
  INCONCLUSIVE:    "badge badge-muted",
  REJECTED:        "badge badge-danger",
};

function SortTh({
  col, label, current, dir, onSort, className,
}: {
  col: SortKey; label: string; current: SortKey; dir: SortDir;
  onSort: (k: SortKey) => void; className?: string;
}) {
  const active = col === current;
  return (
    <th className={`sortable${className ? " " + className : ""}`} onClick={() => onSort(col)}>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
        {label}
        {active ? (
          dir === "desc" ? <ChevronDown size={11} /> : <ChevronUp size={11} />
        ) : null}
      </span>
    </th>
  );
}

export function WorkloadPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("workload_impact_score");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const { data: queries, isLoading } = useQuery({
    queryKey: ["queries", workspaceId],
    queryFn: () => api.queries.list(workspaceId!),
    enabled: !!workspaceId,
  });

  const snapshot = useMutation({
    mutationFn: () => api.snapshots.capture(workspaceId!),
    onSuccess: () => {
      toast.success("Capture started — refreshing in 10s");
      setTimeout(() => qc.invalidateQueries({ queryKey: ["queries", workspaceId] }), 10000);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const displayed = (queries ?? [])
    .filter((q) =>
      !search ||
      q.normalized_sql.toLowerCase().includes(search.toLowerCase())
    )
    .sort((a, b) => {
      const av = ((a as any)[sortKey] as number) ?? 0;
      const bv = ((b as any)[sortKey] as number) ?? 0;
      return sortDir === "desc" ? bv - av : av - bv;
    });

  function handleSort(k: SortKey) {
    if (k === sortKey) setSortDir(d => d === "desc" ? "asc" : "desc");
    else { setSortKey(k); setSortDir("desc"); }
  }

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Workload</h1>
          <p className="page-sub">
            {queries ? `${queries.length} query fingerprints captured` : "Query fingerprints from pg_stat_statements"}
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search queries…"
            className="input"
            style={{ width: 240 }}
          />
          <button
            className="btn btn-primary"
            onClick={() => snapshot.mutate()}
            disabled={snapshot.isPending}
          >
            {snapshot.isPending ? <Loader2 size={13} className="spin" /> : <RefreshCw size={13} />}
            Capture snapshot
          </button>
        </div>
      </div>

      <div className="page-body">
        {isLoading && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {[1,2,3,4,5].map(i => <div key={i} className="skeleton" style={{ height: 48, borderRadius: 6 }} />)}
          </div>
        )}

        {!isLoading && displayed.length === 0 && (
          <div className="empty">
            <Activity size={28} className="empty-icon" />
            <p className="empty-title">{search ? "No matching queries" : "No queries captured"}</p>
            <p className="empty-body">
              {search
                ? "Try a different search term."
                : "Capture a workload snapshot to see queries from pg_stat_statements."}
            </p>
            {!search && (
              <button className="btn btn-primary" style={{ marginTop: 8 }} onClick={() => snapshot.mutate()}>
                <RefreshCw size={13} /> Capture snapshot
              </button>
            )}
          </div>
        )}

        {displayed.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Query</th>
                  <th>Signals</th>
                  <SortTh col="calls" label="Calls" current={sortKey} dir={sortDir} onSort={handleSort} className="r" />
                  <SortTh col="mean_exec_time" label="Avg time" current={sortKey} dir={sortDir} onSort={handleSort} className="r" />
                  <SortTh col="workload_impact_score" label="Impact" current={sortKey} dir={sortDir} onSort={handleSort} />
                </tr>
              </thead>
              <tbody>
                {displayed.map((q) => (
                  <tr
                    key={q.id}
                    onClick={() => navigate(`/workspaces/${workspaceId}/queries/${q.id}`)}
                  >
                    <td style={{ maxWidth: 400 }}>
                      <div className="mono-sm" style={{
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                        maxWidth: 400, color: "var(--text)",
                      }}>
                        {q.normalized_sql.replace(/\s+/g, " ").slice(0, 120)}
                      </div>
                      {q.current_database && (
                        <div style={{ fontSize: 10, color: "var(--text-3)", marginTop: 2 }}>
                          {q.current_database}
                        </div>
                      )}
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                        {q.contains_seq_scan && (
                          <span className="badge badge-warn">seq scan</span>
                        )}
                        {q.recommendation_status && (
                          <span className={REC_BADGE[q.recommendation_status] ?? "badge badge-muted"}>
                            {q.recommendation_status.replace("_", " ").toLowerCase()}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="r mono-sm">{q.calls ? formatNumber(q.calls) : "—"}</td>
                    <td className="r mono-sm">{q.mean_exec_time ? formatMs(q.mean_exec_time) : "—"}</td>
                    <td style={{ width: 100 }}>
                      <div className="impact-bar-wrap">
                        <div
                          className="impact-bar-fill"
                          style={{ width: `${((q.workload_impact_score ?? 0) * 100).toFixed(0)}%` }}
                        />
                      </div>
                      <div className="mono-sm" style={{ color: "var(--text-3)" }}>
                        {((q.workload_impact_score ?? 0) * 100).toFixed(0)}%
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
