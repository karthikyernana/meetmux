import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2, Play, TrendingDown, Layers, ArrowLeft, ArrowRight, AlertTriangle } from "lucide-react";
import { api } from "@/api/client";
import { formatBytes } from "@/lib/utils";

function CostDiff({ before, after }: { before: number; after: number }) {
  const reduction = before > 0 ? ((before - after) / before) * 100 : 0;
  const positive = after < before;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
      <div>
        <div style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase" }}>Before</div>
        <div className="mono-sm" style={{ fontWeight: 600, fontSize: 15, color: "var(--text)" }}>{before.toFixed(1)}</div>
      </div>
      <div style={{
        display: "flex", flexDirection: "column", alignItems: "center",
        color: positive ? "var(--ok)" : "var(--danger)",
      }}>
        <TrendingDown size={14} />
        <span style={{ fontSize: 11, fontWeight: 600 }}>{positive ? "-" : "+"}{Math.abs(reduction).toFixed(1)}%</span>
      </div>
      <div>
        <div style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase" }}>After</div>
        <div className="mono-sm" style={{ fontWeight: 600, fontSize: 15, color: positive ? "var(--ok)" : "var(--text)" }}>
          {after.toFixed(1)}
        </div>
      </div>
    </div>
  );
}

export function ExperimentPage() {
  const { workspaceId, queryId, experimentId } = useParams<{
    workspaceId: string;
    queryId: string;
    experimentId: string;
  }>();
  const navigate = useNavigate();

  const { data: experiment, isLoading } = useQuery({
    queryKey: ["experiment", experimentId],
    queryFn: () => api.experiments.get(experimentId!),
    enabled: !!experimentId,
    refetchInterval: (query) =>
      query.state.data?.status === "running" || query.state.data?.status === "pending"
        ? 1500
        : false,
  });

  const runMutation = useMutation({
    mutationFn: () => api.experiments.run(experimentId!),
    onSuccess: () => toast.success("Experiment simulation started"),
    onError: (e: Error) => toast.error(e.message),
  });

  if (isLoading) {
    return (
      <div className="page-body">
        {[1, 2, 3].map((i) => (
          <div key={i} className="skeleton" style={{ height: 60, marginBottom: 12, borderRadius: 6 }} />
        ))}
      </div>
    );
  }

  if (!experiment) {
    return (
      <div className="page-body" style={{ color: "var(--text-3)" }}>
        Experiment not found.
      </div>
    );
  }

  const diff = experiment.plan_diff;
  const isPending = experiment.status === "pending";
  const isRunning = experiment.status === "running";
  const isComplete = experiment.status === "complete";

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <button
            className="btn btn-ghost btn-sm"
            style={{ marginBottom: 8 }}
            onClick={() => {
              if (workspaceId && queryId) {
                navigate(`/workspaces/${workspaceId}/queries/${queryId}`);
              } else if (workspaceId) {
                navigate(`/workspaces/${workspaceId}/workload`);
              }
            }}
          >
            <ArrowLeft size={12} /> Query detail
          </button>
          <h1 className="page-title">Plan experiment</h1>
          <p className="page-sub">
            Hypothetical execution plan comparison
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {!experiment.hypopg_available && (
            <span className="badge badge-warn">
              HypoPG unavailable · Fallback evaluation
            </span>
          )}
          {(isPending || isComplete) && (
            <button
              onClick={() => runMutation.mutate()}
              disabled={runMutation.isPending || isRunning}
              className="btn btn-primary"
            >
              {runMutation.isPending || isRunning ? (
                <Loader2 size={13} className="spin" />
              ) : (
                <Play size={13} />
              )}
              {isComplete ? "Run again" : "Run experiment"}
            </button>
          )}
          {isComplete && workspaceId && (
            <button
              className="btn btn-secondary"
              onClick={() => navigate(`/workspaces/${workspaceId}/recommendations`)}
            >
              Recommendations <ArrowRight size={13} />
            </button>
          )}
        </div>
      </div>

      <div className="page-body" style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 920 }}>
        {/* Status banner */}
        {isRunning && (
          <div className="alert alert-warn">
            <Loader2 size={14} className="spin" style={{ flexShrink: 0 }} />
            <span>Experiment running — collecting hypothetical execution plan from PostgreSQL…</span>
          </div>
        )}

        {/* Diff summary stats */}
        {isComplete && diff && (
          <div className="stat-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
            <div className="stat-cell">
              <div className="stat-label">PLANNER COST</div>
              <div style={{ marginTop: 6 }}>
                {diff.cost ? (
                  <CostDiff before={diff.cost.before} after={diff.cost.after} />
                ) : (
                  <span className="mono-sm">—</span>
                )}
              </div>
            </div>

            <div className="stat-cell">
              <div className="stat-label">SCAN TYPE</div>
              <div style={{ marginTop: 6 }}>
                {diff.scan_change ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
                    <span className="badge badge-warn">{diff.scan_change.before}</span>
                    <span style={{ color: "var(--text-3)" }}>→</span>
                    <span className="badge badge-ok">{diff.scan_change.after}</span>
                  </div>
                ) : (
                  <span style={{ fontSize: 13, color: "var(--text-2)" }}>No scan change</span>
                )}
              </div>
            </div>

            <div className="stat-cell">
              <div className="stat-label">SORT NODES</div>
              <div style={{ marginTop: 6 }}>
                {diff.sort ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 14 }}>
                    <span className="mono-sm" style={{ fontWeight: 600 }}>{diff.sort.before}</span>
                    <span style={{ color: "var(--text-3)" }}>→</span>
                    <span className="mono-sm" style={{
                      fontWeight: 600,
                      color: diff.sort.after < diff.sort.before ? "var(--ok)" : "inherit"
                    }}>
                      {diff.sort.after}
                    </span>
                    {diff.sort.before > diff.sort.after && (
                      <span className="badge badge-ok">Sort removed</span>
                    )}
                  </div>
                ) : (
                  <span style={{ fontSize: 13, color: "var(--text-2)" }}>No sort change</span>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Storage estimate */}
        {experiment.storage_estimate_bytes && (
          <div className="card">
            <div className="card-body" style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 16px" }}>
              <Layers size={16} style={{ color: "var(--accent-mid)" }} />
              <span style={{ fontSize: 13, color: "var(--text-2)" }}>
                Estimated index size: <strong>{formatBytes(experiment.storage_estimate_bytes)}</strong>
              </span>
            </div>
          </div>
        )}

        {/* Plan JSON comparison */}
        {isComplete && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <div className="card">
              <div className="card-header">
                <span className="card-title mono-sm">Baseline plan (Before)</span>
                {experiment.before_cost != null && (
                  <span className="badge badge-muted">cost {experiment.before_cost.toFixed(1)}</span>
                )}
              </div>
              <pre style={{
                padding: "12px 16px",
                fontSize: 11,
                fontFamily: "var(--font-mono)",
                color: "var(--text-2)",
                maxHeight: 300,
                overflowY: "auto",
                lineHeight: 1.5,
                margin: 0,
              }}>
                {experiment.before_plan_json
                  ? JSON.stringify(experiment.before_plan_json, null, 2)
                  : "No prior plan recorded"}
              </pre>
            </div>

            <div className="card" style={{ borderColor: "var(--ok-border)" }}>
              <div className="card-header" style={{ background: "var(--ok-bg)" }}>
                <span className="card-title mono-sm" style={{ color: "var(--ok)" }}>
                  Hypothetical plan (After)
                </span>
                {experiment.after_cost != null && (
                  <span className="badge badge-ok">cost {experiment.after_cost.toFixed(1)}</span>
                )}
              </div>
              <pre style={{
                padding: "12px 16px",
                fontSize: 11,
                fontFamily: "var(--font-mono)",
                color: "var(--text)",
                maxHeight: 300,
                overflowY: "auto",
                lineHeight: 1.5,
                margin: 0,
              }}>
                {experiment.after_plan_json
                  ? JSON.stringify(experiment.after_plan_json, null, 2)
                  : "Hypothetical plan not available"}
              </pre>
            </div>
          </div>
        )}

        {/* Error state */}
        {experiment.status === "failed" && (
          <div className="alert alert-danger">
            <AlertTriangle size={14} style={{ flexShrink: 0 }} />
            <div>
              <strong>{experiment.error_code ?? "Execution error"}</strong>
              <div style={{ marginTop: 2 }}>{experiment.error_message}</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
