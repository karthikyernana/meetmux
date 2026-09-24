import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2, RefreshCw, FlaskConical, Copy, AlertTriangle, ArrowLeft } from "lucide-react";
import { api } from "@/api/client";
import { formatMs, formatNumber } from "@/lib/utils";

// ── Main Page ─────────────────────────────────────────────────────────────────

type Candidate = {
  id?: string;
  table_name?: string;
  columns?: string[];
  index_method?: string;
  source_signals?: string[];
};

export function QueryDetailPage() {
  const { workspaceId, queryId } = useParams<{ workspaceId: string; queryId: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data: query, isLoading } = useQuery({
    queryKey: ["query", workspaceId, queryId],
    queryFn: () => api.queries.get(workspaceId!, queryId!),
    enabled: !!queryId,
  });

  const { data: candidates } = useQuery({
    queryKey: ["candidates", workspaceId, queryId],
    queryFn: () => api.queries.candidates(workspaceId!, queryId!),
    enabled: !!queryId,
  });

  const analyzeMut = useMutation({
    mutationFn: () => api.queries.analyze(workspaceId!, queryId!),
    onSuccess: () => {
      toast.success("Analysis started");
      setTimeout(() => qc.invalidateQueries({ queryKey: ["query", workspaceId, queryId] }), 3000);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const genMut = useMutation({
    mutationFn: () => api.queries.generateCandidates(workspaceId!, queryId!),
    onSuccess: () => {
      toast.success("Generating candidates…");
      setTimeout(() => qc.invalidateQueries({ queryKey: ["candidates", workspaceId, queryId] }), 3000);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const expMut = useMutation({
    mutationFn: async (candidateId: string) => {
      const exp = await api.experiments.create(candidateId, queryId!);
      await api.experiments.run(exp.id);
      return exp;
    },
    onSuccess: (exp) => {
      toast.success("Simulation experiment launched");
      navigate(`/workspaces/${workspaceId}/queries/${queryId}/experiments/${exp.id}`);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (isLoading) {
    return (
      <div className="page-body">
        {[1, 2, 3].map(i => (
          <div key={i} className="skeleton" style={{ height: 48, marginBottom: 8, borderRadius: 6 }} />
        ))}
      </div>
    );
  }

  if (!query) return <div className="page-body" style={{ color: "var(--text-3)" }}>Query not found.</div>;

  const cands = (candidates ?? []) as Candidate[];

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <button
            className="btn btn-ghost btn-sm"
            style={{ marginBottom: 8 }}
            onClick={() => navigate(`/workspaces/${workspaceId}/workload`)}
          >
            <ArrowLeft size={12} /> Workload
          </button>
          <h1 className="page-title">Query detail</h1>
          <p className="page-sub">
            {query.current_database && <span>{query.current_database} · </span>}
            Impact: {((query.workload_impact_score ?? 0) * 100).toFixed(0)}%
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            className="btn btn-secondary"
            disabled={genMut.isPending}
            onClick={() => genMut.mutate()}
          >
            {genMut.isPending ? <Loader2 size={13} className="spin" /> : <FlaskConical size={13} />}
            Generate candidates
          </button>
          <button
            className="btn btn-primary"
            disabled={analyzeMut.isPending}
            onClick={() => analyzeMut.mutate()}
          >
            {analyzeMut.isPending ? <Loader2 size={13} className="spin" /> : <RefreshCw size={13} />}
            Analyse
          </button>
        </div>
      </div>

      <div className="page-body" style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 880 }}>

        {/* SQL block */}
        <div className="card">
          <div className="card-header">
            <span className="card-title mono-sm">SQL</span>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => { navigator.clipboard.writeText(query.normalized_sql); toast.success("Copied"); }}
            >
              <Copy size={12} /> Copy
            </button>
          </div>
          <pre style={{
            padding: "12px 16px", fontSize: 12, fontFamily: "var(--font-mono)",
            color: "var(--text-2)", whiteSpace: "pre-wrap", overflowX: "auto",
            maxHeight: 200, lineHeight: 1.6, margin: 0,
          }}>
            {query.normalized_sql}
          </pre>
        </div>

        {/* Seq scan warning */}
        {query.contains_seq_scan && (
          <div className="alert alert-warn">
            <AlertTriangle size={14} style={{ flexShrink: 0 }} />
            <span>Sequential scan detected — strong index opportunity signal.</span>
          </div>
        )}

        {/* Metrics */}
        <div className="stat-grid">
          <div className="stat-cell">
            <div className="stat-label">calls</div>
            <div className="stat-value">{query.calls ? formatNumber(query.calls) : "—"}</div>
          </div>
          <div className="stat-cell">
            <div className="stat-label">avg exec time</div>
            <div className="stat-value">{query.mean_exec_time ? formatMs(query.mean_exec_time) : "—"}</div>
          </div>
          <div className="stat-cell">
            <div className="stat-label">total exec time</div>
            <div className="stat-value">{query.total_exec_time ? formatMs(query.total_exec_time) : "—"}</div>
          </div>
          <div className="stat-cell">
            <div className="stat-label">workload impact</div>
            <div className="stat-value">
              {query.workload_impact_score
                ? `${(query.workload_impact_score * 100).toFixed(0)}%`
                : "—"}
            </div>
          </div>
        </div>

        {/* Candidates */}
        <div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>Index candidates</span>
            <span style={{ fontSize: 11, color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>
              {cands.length} generated
            </span>
          </div>

          {cands.length === 0 ? (
            <div className="empty" style={{ padding: "28px 16px", border: "1px dashed var(--border)", borderRadius: 8 }}>
              <FlaskConical size={22} className="empty-icon" />
              <p className="empty-title">No candidates yet</p>
              <p className="empty-body">Click "Generate candidates" to produce index suggestions for this query.</p>
            </div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Table</th>
                    <th>Columns</th>
                    <th>Method</th>
                    <th>Signals</th>
                    <th style={{ width: 130 }}></th>
                  </tr>
                </thead>
                <tbody>
                  {cands.map((c, i) => (
                    <tr key={c.id ?? i} style={{ cursor: "default" }}>
                      <td className="mono-sm">{c.table_name ?? "—"}</td>
                      <td>
                        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                          {(c.columns ?? []).map(col => (
                            <span key={col} className="mono-sm" style={{
                              background: "var(--surface-2)", border: "1px solid var(--border)",
                              borderRadius: 3, padding: "1px 5px",
                            }}>{col}</span>
                          ))}
                        </div>
                      </td>
                      <td><span className="badge badge-muted">{c.index_method ?? "btree"}</span></td>
                      <td>
                        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                          {(c.source_signals ?? []).map(s => (
                            <span key={s} className="badge badge-accent">{s.replace(/_/g, " ").toLowerCase()}</span>
                          ))}
                        </div>
                      </td>
                      <td className="r">
                        <button
                          className="btn btn-secondary btn-sm"
                          disabled={expMut.isPending}
                          onClick={() => {
                            if (c.id) expMut.mutate(c.id);
                            else toast.error("Candidate ID missing");
                          }}
                        >
                          {expMut.isPending ? <Loader2 size={12} className="spin" /> : <FlaskConical size={12} />}
                          Run experiment
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
