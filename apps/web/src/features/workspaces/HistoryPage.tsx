import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { History } from "lucide-react";

type Snapshot = {
  id?: string;
  captured_at?: string;
  status?: string;
  query_count?: number;
  observation_window_start?: string | null;
  observation_window_end?: string | null;
};

export function HistoryPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();

  const { data: snapshots, isLoading } = useQuery({
    queryKey: ["snapshots", workspaceId],
    queryFn: () => api.snapshots.list(workspaceId!),
    enabled: !!workspaceId,
  });

  const items = (snapshots ?? []) as Snapshot[];

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">History</h1>
          <p className="page-sub">
            {items.length > 0 ? `${items.length} workload snapshots` : "Past workload snapshots"}
          </p>
        </div>
      </div>

      <div className="page-body">
        {isLoading && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {[1, 2, 3].map(i => (
              <div key={i} className="skeleton" style={{ height: 48, borderRadius: 6 }} />
            ))}
          </div>
        )}

        {!isLoading && items.length === 0 && (
          <div className="empty">
            <History size={28} className="empty-icon" />
            <p className="empty-title">No snapshots yet</p>
            <p className="empty-body">
              Capture a workload snapshot to start building analysis history.
            </p>
          </div>
        )}

        {items.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Captured</th>
                  <th>Status</th>
                  <th className="r">Queries</th>
                  <th>Window start</th>
                  <th>Window end</th>
                </tr>
              </thead>
              <tbody>
                {items.map((s, i) => (
                  <tr key={s.id ?? i} style={{ cursor: "default" }}>
                    <td>
                      <span className="mono-sm" style={{ color: "var(--text)" }}>
                        {s.captured_at
                          ? new Date(s.captured_at).toLocaleString()
                          : "—"}
                      </span>
                    </td>
                    <td>
                      <span className={`badge ${
                        s.status === "complete" ? "badge-ok" :
                        s.status === "failed"   ? "badge-danger" :
                        s.status === "capturing"? "badge-warn" :
                        "badge-muted"
                      }`}>
                        {s.status ?? "unknown"}
                      </span>
                    </td>
                    <td className="r mono-sm" style={{ color: "var(--text-2)" }}>
                      {s.query_count?.toLocaleString() ?? "—"}
                    </td>
                    <td className="mono-sm" style={{ color: "var(--text-3)" }}>
                      {s.observation_window_start
                        ? new Date(s.observation_window_start).toLocaleString()
                        : "—"}
                    </td>
                    <td className="mono-sm" style={{ color: "var(--text-3)" }}>
                      {s.observation_window_end
                        ? new Date(s.observation_window_end).toLocaleString()
                        : "—"}
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
