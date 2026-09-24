import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/api/client";
import { ConnectionDialog } from "@/features/workspaces/ConnectionDialog";
import { Database, Shield, Cpu, CheckCircle2, AlertCircle, XCircle } from "lucide-react";

function CapRow({ name, status, detail }: { name: string; status: string; detail?: string | null }) {
  const icon =
    status === "ok" ? <CheckCircle2 size={13} style={{ color: "var(--ok)", flexShrink: 0 }} /> :
    status === "warning" ? <AlertCircle size={13} style={{ color: "var(--accent-mid)", flexShrink: 0 }} /> :
    <XCircle size={13} style={{ color: "var(--danger)", flexShrink: 0 }} />;

  return (
    <tr style={{ cursor: "default" }}>
      <td style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {icon}
        <span style={{ fontSize: 12 }}>{name.replace(/_/g, " ")}</span>
      </td>
      <td style={{ fontSize: 12, color: "var(--text-3)" }}>{detail ?? "—"}</td>
    </tr>
  );
}

export function SettingsPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const [connectOpen, setConnectOpen] = useState(false);

  const { data: conn } = useQuery({
    queryKey: ["connection", workspaceId],
    queryFn: () => api.connections.status(workspaceId!),
    enabled: !!workspaceId,
    retry: false,
  });

  const { data: workspace } = useQuery({
    queryKey: ["workspace", workspaceId],
    queryFn: () => api.workspaces.get(workspaceId!),
    enabled: !!workspaceId,
  });

  const capabilities = conn?.capability_status
    ? Object.entries(conn.capability_status as Record<string, { status: string; detail?: string | null }>)
    : [];

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="page-sub">Workspace configuration and database connection</p>
        </div>
      </div>

      <div className="page-body" style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: 680 }}>

        {/* Workspace info */}
        <div className="card">
          <div className="card-header">
            <span className="card-title" style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Shield size={12} /> Workspace
            </span>
          </div>
          <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              <div>
                <div style={{ fontSize: 11, color: "var(--text-3)", marginBottom: 3, fontFamily: "var(--font-mono)" }}>NAME</div>
                <div style={{ fontSize: 13, fontWeight: 500 }}>{workspace?.name ?? "—"}</div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: "var(--text-3)", marginBottom: 3, fontFamily: "var(--font-mono)" }}>ENVIRONMENT</div>
                <div style={{ fontSize: 13 }}>{workspace?.environment_label ?? "—"}</div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: "var(--text-3)", marginBottom: 3, fontFamily: "var(--font-mono)" }}>WORKSPACE ID</div>
                <div className="mono-sm" style={{ color: "var(--text-3)" }}>{workspaceId}</div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: "var(--text-3)", marginBottom: 3, fontFamily: "var(--font-mono)" }}>STATUS</div>
                <span className="badge badge-ok">{workspace?.status ?? "active"}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Connection */}
        <div className="card">
          <div className="card-header">
            <span className="card-title" style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Database size={12} /> Database connection
            </span>
            <button className="btn btn-secondary btn-sm" onClick={() => setConnectOpen(true)}>
              {conn ? "Reconnect" : "Connect"}
            </button>
          </div>
          {conn ? (
            <div className="card-body">
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                {[
                  ["host", conn.host],
                  ["port", String(conn.port)],
                  ["database", conn.database_name],
                  ["username", conn.username],
                  ["ssl mode", conn.ssl_mode],
                  ["server version", conn.server_version ?? "unknown"],
                ].map(([label, val]) => (
                  <div key={label}>
                    <div style={{ fontSize: 11, color: "var(--text-3)", marginBottom: 3, fontFamily: "var(--font-mono)", textTransform: "uppercase" }}>
                      {label}
                    </div>
                    <div className="mono-sm" style={{ color: "var(--text)" }}>{val}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="empty" style={{ padding: "32px 16px" }}>
              <Database size={24} className="empty-icon" />
              <p className="empty-title">Not connected</p>
              <p className="empty-body">Connect a PostgreSQL database to start analysis.</p>
              <button className="btn btn-primary" style={{ marginTop: 8 }} onClick={() => setConnectOpen(true)}>
                <Database size={13} /> Connect database
              </button>
            </div>
          )}
        </div>

        {/* Capabilities */}
        {capabilities.length > 0 && (
          <div className="card">
            <div className="card-header">
              <span className="card-title" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <Cpu size={12} /> Capability check
              </span>
            </div>
            <div style={{ padding: "0 16px 4px" }}>
              <table style={{ width: "100%" }}>
                <thead>
                  <tr>
                    <th style={{ padding: "8px 0", fontSize: 11, color: "var(--text-3)", textAlign: "left", fontFamily: "var(--font-mono)", letterSpacing: "0.04em" }}>
                      FEATURE
                    </th>
                    <th style={{ padding: "8px 0", fontSize: 11, color: "var(--text-3)", textAlign: "left", fontFamily: "var(--font-mono)", letterSpacing: "0.04em" }}>
                      DETAIL
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {capabilities.map(([name, v]) => (
                    <CapRow key={name} name={name} status={v.status} detail={v.detail} />
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
