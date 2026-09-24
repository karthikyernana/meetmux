import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Database, RefreshCw, AlertTriangle, Loader2, ArrowRight } from "lucide-react";
import { api } from "@/api/client";
import { formatNumber, formatMs } from "@/lib/utils";
import { ConnectionDialog } from "./ConnectionDialog";

const REC_BADGE: Record<string, string> = {
  RECOMMENDED:     "badge badge-ok",
  REVIEW_REQUIRED: "badge badge-warn",
  INCONCLUSIVE:    "badge badge-muted",
  REJECTED:        "badge badge-danger",
};

export function WorkspaceOverviewPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [connectOpen, setConnectOpen] = useState(false);

  const { data: workspace, isLoading } = useQuery({
    queryKey: ["workspace", workspaceId],
    queryFn: () => api.workspaces.get(workspaceId!),
    enabled: !!workspaceId,
  });

  const { data: connection } = useQuery({
    queryKey: ["connection", workspaceId],
    queryFn: () => api.connections.status(workspaceId!),
    enabled: !!workspaceId,
    retry: false,
  });

  const { data: queries } = useQuery({
    queryKey: ["queries", workspaceId],
    queryFn: () => api.queries.list(workspaceId!),
    enabled: !!workspaceId,
  });

  const { data: recommendations } = useQuery({
    queryKey: ["recommendations", workspaceId],
    queryFn: () => api.recommendations.list(workspaceId!),
    enabled: !!workspaceId,
  });

  const snapshot = useMutation({
    mutationFn: () => api.snapshots.capture(workspaceId!),
    onSuccess: () => {
      toast.success("Workload capture started");
      qc.invalidateQueries({ queryKey: ["workspace", workspaceId] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (isLoading) {
    return (
      <div className="page-body">
        {[1, 2, 3].map((i) => <div key={i} className="skeleton" style={{ height: 48, marginBottom: 8, borderRadius: 6 }} />)}
      </div>
    );
  }

  if (!workspace) return null;

  const warnings = connection?.capability_status
    ? Object.entries(connection.capability_status)
        .filter(([, v]) => (v as any).status !== "ok")
        .map(([k, v]) => ({ name: k, detail: (v as any).detail }))
    : [];

  const highImpact = queries?.filter(q => (q.workload_impact_score ?? 0) > 0.6).length ?? 0;
  const recommended = recommendations?.filter(r => r.status === "RECOMMENDED").length ?? 0;

  return (
    <div className="fade-in">
      {/* Header */}
      <div className="page-header">
        <div>
          <div style={{ fontSize: 11, color: "var(--text-3)", marginBottom: 4, fontFamily: "var(--font-mono)" }}>
            WORKSPACE
          </div>
          <h1 className="page-title">{workspace.name}</h1>
          <p className="page-sub">{workspace.environment_label} environment</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-secondary" onClick={() => setConnectOpen(true)}>
            <Database size={13} />
            {connection ? "Reconnect" : "Connect database"}
          </button>
          {connection && (
            <button
              className="btn btn-primary"
              onClick={() => snapshot.mutate()}
              disabled={snapshot.isPending}
            >
              {snapshot.isPending ? <Loader2 size={13} className="spin" /> : <RefreshCw size={13} />}
              Capture workload
            </button>
          )}
        </div>
      </div>

      <div className="page-body" style={{ display: "flex", flexDirection: "column", gap: 20 }}>

        {/* Warnings */}
        {warnings.map(w => (
          <div key={w.name} className="alert alert-warn">
            <AlertTriangle size={14} style={{ flexShrink: 0 }} />
            <span>
              <strong>{w.name.replace(/_/g, " ")}</strong>
              {w.detail ? ` — ${w.detail}` : ""}
            </span>
          </div>
        ))}

        {/* No connection */}
        {!connection && (
          <div className="card" style={{ borderStyle: "dashed" }}>
            <div className="empty">
              <Database size={28} className="empty-icon" />
              <p className="empty-title">No database connected</p>
              <p className="empty-body">
                Connect a PostgreSQL database to begin capturing workload data and generating index recommendations.
              </p>
              <button className="btn btn-primary" style={{ marginTop: 8 }} onClick={() => setConnectOpen(true)}>
                <Database size={13} /> Connect database
              </button>
            </div>
          </div>
        )}

        {/* Stats */}
        <div className="stat-grid">
          <div className="stat-cell">
            <div className="stat-label">queries tracked</div>
            <div className="stat-value">{formatNumber(queries?.length ?? 0)}</div>
            <div className="stat-sub">unique fingerprints</div>
          </div>
          <div className="stat-cell">
            <div className="stat-label">high impact</div>
            <div className="stat-value">{formatNumber(highImpact)}</div>
            <div className="stat-sub">above 60% impact score</div>
          </div>
          <div className="stat-cell">
            <div className="stat-label">recommendations</div>
            <div className="stat-value">{formatNumber(recommendations?.length ?? 0)}</div>
            <div className="stat-sub">{recommended} recommended</div>
          </div>
          <div className="stat-cell">
            <div className="stat-label">last snapshot</div>
            <div className="stat-value" style={{ fontSize: 16 }}>
              {workspace.last_snapshot_at
                ? new Date(workspace.last_snapshot_at).toLocaleDateString()
                : "—"}
            </div>
            <div className="stat-sub">
              {workspace.last_snapshot_at
                ? new Date(workspace.last_snapshot_at).toLocaleTimeString()
                : "no data yet"}
            </div>
          </div>
        </div>

        {/* High-impact queries */}
        {queries && queries.length > 0 && (
          <div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
              <span style={{ fontSize: 13, fontWeight: 600 }}>Top queries by workload impact</span>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => navigate(`/workspaces/${workspaceId}/workload`)}
              >
                View all <ArrowRight size={12} />
              </button>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Query</th>
                    <th className="r">Calls</th>
                    <th className="r">Avg time</th>
                    <th>Status</th>
                    <th style={{ width: 80 }}>Impact</th>
                  </tr>
                </thead>
                <tbody>
                  {queries.slice(0, 8).map((q) => (
                    <tr
                      key={q.id}
                      onClick={() => navigate(`/workspaces/${workspaceId}/queries/${q.id}`)}
                    >
                      <td style={{ maxWidth: 420 }}>
                        <div className="mono-sm" style={{
                          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                          color: "var(--text-2)", maxWidth: 420,
                        }}>
                          {q.normalized_sql.replace(/\s+/g, " ").slice(0, 120)}
                        </div>
                      </td>
                      <td className="r mono-sm">{q.calls ? formatNumber(q.calls) : "—"}</td>
                      <td className="r mono-sm">{q.mean_exec_time ? formatMs(q.mean_exec_time) : "—"}</td>
                      <td>
                        {q.recommendation_status ? (
                          <span className={REC_BADGE[q.recommendation_status] ?? "badge badge-muted"}>
                            {q.recommendation_status.replace("_", " ").toLowerCase()}
                          </span>
                        ) : (
                          <span className="badge badge-muted">pending</span>
                        )}
                      </td>
                      <td>
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
          </div>
        )}
      </div>

      <ConnectionDialog
        workspaceId={workspaceId!}
        open={connectOpen}
        onClose={() => setConnectOpen(false)}
      />
    </div>
  );
}
