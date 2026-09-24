import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { formatBytes } from "@/lib/utils";
import { Table2 } from "lucide-react";

type IndexRecord = {
  id?: string;
  index_name?: string;
  table_name?: string;
  schema_name?: string;
  columns?: string[];
  index_method?: string;
  is_unique?: boolean;
  is_primary?: boolean;
  index_size_bytes?: number | null;
  idx_scan?: number | null;
};

export function IndexInventoryPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();

  const { data, isLoading } = useQuery({
    queryKey: ["indexes", workspaceId],
    queryFn: () => api.indexes.list(workspaceId!),
    enabled: !!workspaceId,
  });

  const indexes = (data ?? []) as IndexRecord[];

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Index inventory</h1>
          <p className="page-sub">
            {indexes.length > 0
              ? `${indexes.length} indexes on the target database`
              : "Existing indexes discovered from pg_stat_user_indexes"}
          </p>
        </div>
      </div>

      <div className="page-body">
        {isLoading && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {[1,2,3,4].map(i => (
              <div key={i} className="skeleton" style={{ height: 44, borderRadius: 6 }} />
            ))}
          </div>
        )}

        {!isLoading && indexes.length === 0 && (
          <div className="empty">
            <Table2 size={28} className="empty-icon" />
            <p className="empty-title">No indexes discovered</p>
            <p className="empty-body">
              Run a workload capture to populate the index inventory from the target database.
            </p>
          </div>
        )}

        {indexes.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Index name</th>
                  <th>Table</th>
                  <th>Columns</th>
                  <th>Method</th>
                  <th>Type</th>
                  <th className="r">Size</th>
                  <th className="r">Scans</th>
                </tr>
              </thead>
              <tbody>
                {indexes.map((idx, i) => (
                  <tr key={idx.id ?? i} style={{ cursor: "default" }}>
                    <td>
                      <span className="mono-sm" style={{ color: "var(--text)" }}>
                        {idx.index_name ?? "—"}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontSize: 12, color: "var(--text-2)" }}>
                        {idx.schema_name !== "public" ? `${idx.schema_name}.` : ""}
                        {idx.table_name ?? "—"}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                        {(idx.columns ?? []).map((col) => (
                          <span key={col} className="mono-sm" style={{
                            background: "var(--surface-2)", border: "1px solid var(--border)",
                            borderRadius: 3, padding: "1px 5px",
                          }}>
                            {col}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td>
                      <span className="badge badge-muted">{idx.index_method ?? "btree"}</span>
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 4 }}>
                        {idx.is_primary && <span className="badge badge-accent">primary</span>}
                        {idx.is_unique && !idx.is_primary && <span className="badge badge-muted">unique</span>}
                        {!idx.is_primary && !idx.is_unique && <span style={{ color: "var(--text-3)", fontSize: 11 }}>—</span>}
                      </div>
                    </td>
                    <td className="r mono-sm" style={{ color: "var(--text-2)" }}>
                      {idx.index_size_bytes != null ? formatBytes(idx.index_size_bytes) : "—"}
                    </td>
                    <td className="r mono-sm" style={{ color: "var(--text-2)" }}>
                      {idx.idx_scan != null ? idx.idx_scan.toLocaleString() : "—"}
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
