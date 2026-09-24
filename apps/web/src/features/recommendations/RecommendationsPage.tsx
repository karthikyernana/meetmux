import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, type RecommendationOut } from "@/api/client";
import { ArrowRight, Sparkles, CheckCircle2, AlertTriangle, HelpCircle, XCircle } from "lucide-react";

const STATUS_BADGE: Record<string, string> = {
  RECOMMENDED:     "badge badge-ok",
  REVIEW_REQUIRED: "badge badge-warn",
  INCONCLUSIVE:    "badge badge-muted",
  REJECTED:        "badge badge-danger",
};

const STATUS_LABEL: Record<string, string> = {
  RECOMMENDED:     "Recommended",
  REVIEW_REQUIRED: "Review required",
  INCONCLUSIVE:    "Inconclusive",
  REJECTED:        "Rejected",
};

function EvidenceBadge({ q }: { q: string }) {
  const cls = q === "HIGH" ? "badge badge-ok" : q === "MEDIUM" ? "badge badge-warn" : "badge badge-muted";
  return <span className={cls}>{q.toLowerCase()} evidence</span>;
}

function RecRow({ rec, onClick }: { rec: RecommendationOut; onClick: () => void }) {
  return (
    <tr onClick={onClick}>
      <td>
        <span className={STATUS_BADGE[rec.status] ?? "badge badge-muted"}>
          {STATUS_LABEL[rec.status] ?? rec.status}
        </span>
      </td>
      <td style={{ maxWidth: 380 }}>
        {rec.explanation ? (
          <div style={{
            fontSize: 13, color: "var(--text-2)",
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 380,
          }}>
            {rec.explanation}
          </div>
        ) : (
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {rec.reason_codes.slice(0, 3).map((rc) => (
              <span key={rc} className="badge badge-muted">{rc.replace(/_/g, " ").toLowerCase()}</span>
            ))}
            {rec.reason_codes.length > 3 && (
              <span style={{ fontSize: 11, color: "var(--text-3)" }}>+{rec.reason_codes.length - 3}</span>
            )}
          </div>
        )}
      </td>
      <td>
        {rec.evidence_quality && <EvidenceBadge q={rec.evidence_quality} />}
      </td>
      <td className="r mono-sm" style={{ color: "var(--text-2)" }}>
        {rec.score != null ? rec.score.toFixed(2) : "—"}
      </td>
      <td className="r">
        <ArrowRight size={14} style={{ color: "var(--text-3)" }} />
      </td>
    </tr>
  );
}

export function RecommendationsPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const navigate = useNavigate();

  const { data: recs, isLoading } = useQuery({
    queryKey: ["recommendations", workspaceId],
    queryFn: () => api.recommendations.list(workspaceId!),
    enabled: !!workspaceId,
  });

  const groups: [string, RecommendationOut[]][] = recs
    ? [
        ["RECOMMENDED", recs.filter(r => r.status === "RECOMMENDED")],
        ["REVIEW_REQUIRED", recs.filter(r => r.status === "REVIEW_REQUIRED")],
        ["INCONCLUSIVE", recs.filter(r => r.status === "INCONCLUSIVE")],
        ["REJECTED", recs.filter(r => r.status === "REJECTED")],
      ].filter(([, arr]) => (arr as RecommendationOut[]).length > 0) as [string, RecommendationOut[]][]
    : [];

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Recommendations</h1>
          <p className="page-sub">
            {recs ? `${recs.length} index candidates evaluated` : "Evidence-based index recommendations"}
          </p>
        </div>
      </div>

      <div className="page-body" style={{ display: "flex", flexDirection: "column", gap: 24 }}>
        {isLoading && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {[1,2,3].map(i => <div key={i} className="skeleton" style={{ height: 48, borderRadius: 6 }} />)}
          </div>
        )}

        {!isLoading && recs?.length === 0 && (
          <div className="empty">
            <Sparkles size={28} className="empty-icon" />
            <p className="empty-title">No recommendations yet</p>
            <p className="empty-body">
              Capture a workload snapshot and run analysis to generate index recommendations.
            </p>
          </div>
        )}

        {groups.map(([status, items]) => (
          <div key={status}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
              {status === "RECOMMENDED" && <CheckCircle2 size={14} style={{ color: "var(--ok)" }} />}
              {status === "REVIEW_REQUIRED" && <AlertTriangle size={14} style={{ color: "var(--accent-mid)" }} />}
              {status === "INCONCLUSIVE" && <HelpCircle size={14} style={{ color: "var(--muted)" }} />}
              {status === "REJECTED" && <XCircle size={14} style={{ color: "var(--danger)" }} />}
              <span style={{ fontSize: 13, fontWeight: 600 }}>
                {STATUS_LABEL[status]}
              </span>
              <span style={{
                fontSize: 11, color: "var(--text-3)", fontFamily: "var(--font-mono)",
                background: "var(--surface-2)", border: "1px solid var(--border)",
                borderRadius: 20, padding: "1px 7px",
              }}>
                {items.length}
              </span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th style={{ width: 140 }}>Status</th>
                    <th>Summary</th>
                    <th style={{ width: 140 }}>Evidence</th>
                    <th className="r" style={{ width: 80 }}>Score</th>
                    <th style={{ width: 40 }}></th>
                  </tr>
                </thead>
                <tbody>
                  {items.map(rec => (
                    <RecRow
                      key={rec.id}
                      rec={rec}
                      onClick={() => navigate(`/workspaces/${workspaceId}/recommendations/${rec.id}`)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
