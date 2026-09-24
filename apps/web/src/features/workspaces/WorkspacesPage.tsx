import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Plus, Database, AlertCircle, ArrowRight, Trash2, Loader2, X } from "lucide-react";
import { toast } from "sonner";
import { api, type WorkspaceOut } from "@/api/client";

const schema = z.object({
  name: z.string().min(1, "Name is required").max(255),
  environment_label: z.enum(["production", "staging", "development", "testing"]),
});
type FormData = z.infer<typeof schema>;

const ENV_BADGE: Record<string, string> = {
  production: "badge badge-danger",
  staging:    "badge badge-warn",
  development:"badge badge-ok",
  testing:    "badge badge-muted",
};

function NewWorkspaceDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { register, handleSubmit, formState: { errors }, reset } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { environment_label: "development" },
  });

  const create = useMutation({
    mutationFn: (data: FormData) => api.workspaces.create(data),
    onSuccess: (ws) => {
      qc.invalidateQueries({ queryKey: ["workspaces"] });
      toast.success(`"${ws.name}" created`);
      reset();
      onClose();
      navigate(`/workspaces/${ws.id}`);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (!open) return null;

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-header">
          <span className="dialog-title">New workspace</span>
          <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close">
            <X size={14} />
          </button>
        </div>
        <form onSubmit={handleSubmit((d) => create.mutate(d))}>
          <div className="dialog-body">
            <p style={{ fontSize: 13, color: "var(--text-2)", lineHeight: 1.5 }}>
              A workspace represents one PostgreSQL environment. Connect it to a database to start capturing workload data.
            </p>
            <div className="field">
              <label className="field-label">Name</label>
              <input {...register("name")} placeholder="e.g. api-production" className="input" />
              {errors.name && <span className="field-hint" style={{ color: "var(--danger)" }}>{errors.name.message}</span>}
            </div>
            <div className="field">
              <label className="field-label">Environment</label>
              <select {...register("environment_label")} className="input">
                <option value="development">Development</option>
                <option value="staging">Staging</option>
                <option value="production">Production</option>
                <option value="testing">Testing</option>
              </select>
            </div>
          </div>
          <div className="dialog-footer">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={create.isPending}>
              {create.isPending && <Loader2 size={13} className="spin" />}
              Create workspace
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function WorkspaceRow({
  ws,
  onOpen,
  onDelete,
}: {
  ws: WorkspaceOut;
  onOpen: () => void;
  onDelete: () => void;
}) {
  return (
    <tr onClick={onOpen} style={{ cursor: "pointer" }}>
      <td>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 30, height: 30, borderRadius: 4, background: "var(--surface-2)",
            border: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0,
          }}>
            <Database size={14} style={{ color: "var(--text-3)" }} />
          </div>
          <div>
            <div style={{ fontWeight: 500, color: "var(--text)" }}>{ws.name}</div>
            <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 1 }}>
              {ws.last_snapshot_at
                ? `Snapshot ${new Date(ws.last_snapshot_at).toLocaleDateString()}`
                : "No snapshots"}
            </div>
          </div>
        </div>
      </td>
      <td>
        <span className={ENV_BADGE[ws.environment_label] ?? "badge badge-muted"}>
          {ws.environment_label}
        </span>
      </td>
      <td>
        <span className={`badge ${ws.connection_state === "connected" ? "badge-ok" : "badge-muted"}`}>
          {ws.connection_state ?? "not connected"}
        </span>
      </td>
      <td className="r" style={{ color: "var(--text-2)" }}>
        {ws.open_recommendation_count ?? 0}
      </td>
      <td className="r">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 4 }}>
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
            className="btn btn-ghost btn-sm"
            aria-label="Delete"
            style={{ opacity: 0.4 }}
            onMouseEnter={(e) => (e.currentTarget.style.opacity = "1")}
            onMouseLeave={(e) => (e.currentTarget.style.opacity = "0.4")}
          >
            <Trash2 size={13} />
          </button>
          <ArrowRight size={14} style={{ color: "var(--text-3)" }} />
        </div>
      </td>
    </tr>
  );
}

export function WorkspacesPage() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data: workspaces, isLoading, error } = useQuery({
    queryKey: ["workspaces"],
    queryFn: () => api.workspaces.list(),
  });

  const del = useMutation({
    mutationFn: (id: string) => api.workspaces.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["workspaces"] }); toast.success("Deleted"); },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Workspaces</h1>
          <p className="page-sub">Each workspace connects to one PostgreSQL environment.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setOpen(true)}>
          <Plus size={14} /> New workspace
        </button>
      </div>

      <div className="page-body">
        {/* Error */}
        {error && (
          <div className="alert alert-danger" style={{ marginBottom: 16 }}>
            <AlertCircle size={15} style={{ flexShrink: 0, marginTop: 1 }} />
            <span>Could not reach the API. Make sure the backend is running on port 8000.</span>
          </div>
        )}

        {/* Loading */}
        {isLoading && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {[1, 2, 3].map((i) => (
              <div key={i} className="skeleton" style={{ height: 52, borderRadius: 6 }} />
            ))}
          </div>
        )}

        {/* Empty */}
        {!isLoading && !error && workspaces?.length === 0 && (
          <div className="empty">
            <Database size={32} className="empty-icon" />
            <p className="empty-title">No workspaces</p>
            <p className="empty-body">
              Create a workspace and connect it to a PostgreSQL database to start capturing workload data.
            </p>
            <button className="btn btn-primary" style={{ marginTop: 8 }} onClick={() => setOpen(true)}>
              <Plus size={14} /> New workspace
            </button>
          </div>
        )}

        {/* Table */}
        {workspaces && workspaces.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Workspace</th>
                  <th>Environment</th>
                  <th>Connection</th>
                  <th className="r">Open recommendations</th>
                  <th className="r" style={{ width: 60 }}></th>
                </tr>
              </thead>
              <tbody>
                {workspaces.map((ws) => (
                  <WorkspaceRow
                    key={ws.id}
                    ws={ws}
                    onOpen={() => navigate(`/workspaces/${ws.id}`)}
                    onDelete={() => del.mutate(ws.id)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <NewWorkspaceDialog open={open} onClose={() => setOpen(false)} />
    </div>
  );
}
