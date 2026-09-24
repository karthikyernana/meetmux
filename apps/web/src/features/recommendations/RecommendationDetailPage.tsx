import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useState } from "react";
import {
  CheckCircle2, AlertTriangle, HelpCircle, XCircle,
  Copy, Download, Loader2, ChevronDown, ChevronUp, Info, ArrowLeft
} from "lucide-react";
import { api } from "@/api/client";
import { useNavigate } from "react-router-dom";

const STATUS_BADGE: Record<string, string> = {
  RECOMMENDED:     "badge badge-ok",
  REVIEW_REQUIRED: "badge badge-warn",
  INCONCLUSIVE:    "badge badge-muted",
  REJECTED:        "badge badge-danger",
};

function SqlBlock({ sql, label }: { sql: string; label: string }) {
  const copy = () => { navigator.clipboard.writeText(sql); toast.success("Copied"); };
  const download = () => {
    const blob = new Blob([sql], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "migration.sql"; a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title mono-sm">{label}</span>
        <div style={{ display: "flex", gap: 6 }}>
          <button className="btn btn-ghost btn-sm" onClick={copy}>
            <Copy size={12} /> Copy
          </button>
          <button className="btn btn-ghost btn-sm" onClick={download}>
            <Download size={12} /> Download
          </button>
        </div>
      </div>
      <pre style={{
        padding: "12px 16px", fontSize: 12, fontFamily: "var(--font-mono)",
        color: "var(--ok)", whiteSpace: "pre-wrap", overflowX: "auto",
        lineHeight: 1.6, margin: 0,
      }}>{sql}</pre>
    </div>
  );
}

function ReasonList({ codes, label }: { codes: string[]; label: string }) {
  if (!codes.length) return null;
  return (
    <div>
      <div style={{ fontSize: 11, color: "var(--text-3)", marginBottom: 6, fontFamily: "var(--font-mono)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
        {label}
      </div>
      <ul style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {codes.map(code => (
          <li key={code} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
            <span style={{ color: "var(--text-3)" }}>·</span>
            <span style={{ color: "var(--text-2)" }}>{code.replace(/_/g, " ").toLowerCase()}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function RecommendationDetailPage() {
  const { workspaceId, recommendationId } = useParams<{ workspaceId: string; recommendationId: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [rollbackExpanded, setRollbackExpanded] = useState(false);

  const { data: rec, isLoading } = useQuery({
    queryKey: ["recommendation", recommendationId],
    queryFn: () => api.recommendations.get(recommendationId!),
    enabled: !!recommendationId,
  });

  const migMut = useMutation({
    mutationFn: () => api.recommendations.generateMigration(recommendationId!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["migration", recommendationId] });
      toast.success("Migration SQL generated");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (isLoading) {
    return (
      <div className="page-body">
        {[1, 2, 3].map(i => <div key={i} className="skeleton" style={{ height: 60, marginBottom: 10, borderRadius: 6 }} />)}
      </div>
    );
  }
  if (!rec) return <div className="page-body" style={{ color: "var(--text-3)" }}>Recommendation not found.</div>;

  const observedCodes   = rec.reason_codes.filter(rc => ["HIGH_TOTAL_EXECUTION_TIME","HIGH_CALL_FREQUENCY","SEQ_SCAN_ON_LARGE_RELATION"].includes(rc));
  const derivedCodes    = rec.reason_codes.filter(rc => ["FILTER_MATCH","ORDERING_MATCH","EXISTING_INDEX_OVERLAP","MULTI_QUERY_BENEFIT"].includes(rc));
  const hypotheticalCodes = rec.reason_codes.filter(rc => ["PLAN_COST_REDUCTION","SORT_REMOVED","HYPOPG_UNAVAILABLE"].includes(rc));
  const warningCodes    = rec.reason_codes.filter(rc => ["HIGH_STORAGE_COST","HIGH_WRITE_ACTIVITY","LOW_EVIDENCE"].includes(rc));

  const StatusIcon =
    rec.status === "RECOMMENDED" ? CheckCircle2 :
    rec.status === "REVIEW_REQUIRED" ? AlertTriangle :
    rec.status === "REJECTED" ? XCircle :
    HelpCircle;

  const iconColor =
    rec.status === "RECOMMENDED" ? "var(--ok)" :
    rec.status === "REVIEW_REQUIRED" ? "var(--accent-mid)" :
    rec.status === "REJECTED" ? "var(--danger)" :
    "var(--muted)";

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <button
            className="btn btn-ghost btn-sm"
            style={{ marginBottom: 8 }}
            onClick={() => navigate(`/workspaces/${workspaceId}/recommendations`)}
          >
            <ArrowLeft size={12} /> Recommendations
          </button>
          <h1 className="page-title">Recommendation detail</h1>
        </div>
      </div>

      <div className="page-body" style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 760 }}>

        {/* Status hero */}
        <div className="card">
          <div className="card-body" style={{ display: "flex", alignItems: "flex-start", gap: 16 }}>
            <div style={{
              width: 44, height: 44, borderRadius: 8, flexShrink: 0,
              display: "flex", alignItems: "center", justifyContent: "center",
              border: `1px solid ${iconColor}40`, background: `${iconColor}10`,
            }}>
              <StatusIcon size={20} style={{ color: iconColor }} />
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <span className={STATUS_BADGE[rec.status] ?? "badge badge-muted"}>
                  {rec.status.replace(/_/g, " ").toLowerCase()}
                </span>
                {rec.evidence_quality && (
                  <span className={`badge ${rec.evidence_quality === "HIGH" ? "badge-ok" : rec.evidence_quality === "MEDIUM" ? "badge-warn" : "badge-muted"}`}>
                    {rec.evidence_quality.toLowerCase()} evidence
                  </span>
                )}
                {rec.jev_review_path && (
                  <span className="badge badge-warn">JEV: {rec.jev_review_path.replace(/_/g, " ").toLowerCase()}</span>
                )}
              </div>
              {rec.score != null && (
                <div className="mono-sm" style={{ color: "var(--text-3)" }}>
                  score {rec.score.toFixed(2)}
                  {rec.benefit_score != null ? ` · benefit ${rec.benefit_score.toFixed(2)}` : ""}
                  {rec.storage_penalty ? ` · storage −${rec.storage_penalty.toFixed(2)}` : ""}
                  {rec.write_penalty ? ` · write −${rec.write_penalty.toFixed(2)}` : ""}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Evidence chain */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">Evidence chain</span>
          </div>
          <div className="card-body" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
            <ReasonList codes={observedCodes}     label="Observed facts" />
            <ReasonList codes={derivedCodes}      label="Derived analysis" />
            <ReasonList codes={hypotheticalCodes} label="Hypothetical evidence" />
            {warningCodes.length > 0 && <ReasonList codes={warningCodes} label="Warnings / trade-offs" />}
          </div>
        </div>

        {/* Explanations */}
        {rec.explanation && (
          <div className="card">
            <div className="card-header"><span className="card-title">Analysis summary</span></div>
            <div className="card-body" style={{ fontSize: 13, color: "var(--text-2)", lineHeight: 1.7 }}>
              {rec.explanation}
            </div>
          </div>
        )}

        {rec.ai_explanation && (
          <div className="card" style={{ borderColor: "var(--accent-muted)" }}>
            <div className="card-header">
              <span className="card-title" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <Info size={12} /> AI explanation
              </span>
              <span className="badge badge-muted">explanatory only</span>
            </div>
            <div className="card-body" style={{ fontSize: 13, color: "var(--text-2)", lineHeight: 1.7 }}>
              {rec.ai_explanation}
            </div>
          </div>
        )}

        {/* Migration SQL */}
        {!migMut.data ? (
          <div className="empty" style={{ border: "1px dashed var(--border)", borderRadius: 8, padding: "28px 16px" }}>
            <Download size={24} className="empty-icon" />
            <p className="empty-title">Generate migration SQL</p>
            <p className="empty-body">
              Produces a <code style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>CREATE INDEX CONCURRENTLY</code> statement.
              Review carefully before running in production.
            </p>
            <button
              className="btn btn-primary"
              style={{ marginTop: 10 }}
              disabled={migMut.isPending}
              onClick={() => migMut.mutate()}
            >
              {migMut.isPending && <Loader2 size={13} className="spin" />}
              Generate migration SQL
            </button>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div className="alert alert-warn">
              <AlertTriangle size={14} style={{ flexShrink: 0 }} />
              <span>Review carefully before executing in production. PlanGuard does not run migrations.</span>
            </div>
            <SqlBlock sql={migMut.data.sql_text} label={`CREATE INDEX — ${migMut.data.index_name}`} />
            {migMut.data.rollback_sql_text && (
              <div>
                <button
                  className="btn btn-ghost btn-sm"
                  style={{ marginBottom: 8 }}
                  onClick={() => setRollbackExpanded(!rollbackExpanded)}
                >
                  {rollbackExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                  {rollbackExpanded ? "Hide" : "Show"} rollback SQL
                </button>
                {rollbackExpanded && (
                  <SqlBlock sql={migMut.data.rollback_sql_text} label="Rollback — DROP INDEX" />
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
