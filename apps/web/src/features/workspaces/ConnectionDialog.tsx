import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { Loader2, CheckCircle2, AlertCircle, XCircle, X } from "lucide-react";
import { api, type ConnectionCreate, type CapabilityCheck } from "@/api/client";

const schema = z.object({
  host: z.string().min(1, "Required"),
  port: z.number().int().min(1).max(65535),
  database_name: z.string().min(1, "Required"),
  username: z.string().min(1, "Required"),
  password: z.string().min(1, "Required"),
  ssl_mode: z.enum(["disable", "allow", "prefer", "require", "verify-ca", "verify-full"]),
});
type FormData = z.infer<typeof schema>;

function CapRow({ check }: { check: CapabilityCheck }) {
  const icon =
    check.status === "ok" ? <CheckCircle2 size={14} style={{ color: "var(--ok)" }} /> :
    check.status === "warning" ? <AlertCircle size={14} style={{ color: "var(--accent-mid)" }} /> :
    <XCircle size={14} style={{ color: "var(--danger)" }} />;

  return (
    <div style={{
      display: "flex", alignItems: "flex-start", gap: 10, padding: "8px 0",
      borderBottom: "1px solid var(--border)",
    }}>
      <div style={{ flexShrink: 0, marginTop: 1 }}>{icon}</div>
      <div>
        <div style={{ fontSize: 12, fontWeight: 500, color: "var(--text)" }}>
          {check.name.replace(/_/g, " ")}
        </div>
        {check.detail && (
          <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 2 }}>{check.detail}</div>
        )}
      </div>
    </div>
  );
}

export function ConnectionDialog({
  workspaceId,
  open,
  onClose,
}: {
  workspaceId: string;
  open: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [testResult, setTestResult] = useState<{ success: boolean; capabilities: CapabilityCheck[]; server_version?: string | null } | null>(null);

  const { register, handleSubmit, getValues, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { host: "localhost", port: 5432, ssl_mode: "prefer" },
  });

  const testMut = useMutation({
    mutationFn: (data: ConnectionCreate) => api.connections.test(workspaceId, data),
    onSuccess: (r) => {
      setTestResult(r);
      if (r.success) toast.success(`Connected — ${r.server_version ?? "PostgreSQL"}`);
      else toast.error(r.error ?? "Connection failed");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const saveMut = useMutation({
    mutationFn: (data: ConnectionCreate) => api.connections.save(workspaceId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["connection", workspaceId] });
      qc.invalidateQueries({ queryKey: ["workspace", workspaceId] });
      toast.success("Connection saved");
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (!open) return null;

  return (
    <div className="overlay" onClick={onClose}>
      <div
        className="dialog"
        style={{ maxWidth: 520, maxHeight: "90vh", overflowY: "auto" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="dialog-header">
          <span className="dialog-title">Connect database</span>
          <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close">
            <X size={14} />
          </button>
        </div>

        <form>
          <div className="dialog-body">
            <p style={{ fontSize: 13, color: "var(--text-2)", lineHeight: 1.5 }}>
              PlanGuard connects read-only to analyze workload and run hypothetical experiments. Credentials are encrypted at rest.
            </p>

            {/* Host + Port */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 100px", gap: 10 }}>
              <div className="field">
                <label className="field-label">Host</label>
                <input {...register("host")} placeholder="localhost" className="input" />
                {errors.host && <span className="field-hint" style={{ color: "var(--danger)" }}>{errors.host.message}</span>}
              </div>
              <div className="field">
                <label className="field-label">Port</label>
                <input {...register("port", { valueAsNumber: true })} type="number" placeholder="5432" className="input" />
              </div>
            </div>

            {/* DB name */}
            <div className="field">
              <label className="field-label">Database name</label>
              <input {...register("database_name")} placeholder="my_database" className="input" />
              {errors.database_name && <span className="field-hint" style={{ color: "var(--danger)" }}>{errors.database_name.message}</span>}
            </div>

            {/* Username + Password */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <div className="field">
                <label className="field-label">Username</label>
                <input {...register("username")} placeholder="postgres" className="input" />
                {errors.username && <span className="field-hint" style={{ color: "var(--danger)" }}>{errors.username.message}</span>}
              </div>
              <div className="field">
                <label className="field-label">Password</label>
                <input {...register("password")} type="password" placeholder="••••••••" className="input" />
                {errors.password && <span className="field-hint" style={{ color: "var(--danger)" }}>{errors.password.message}</span>}
              </div>
            </div>

            {/* SSL */}
            <div className="field">
              <label className="field-label">SSL mode</label>
              <select {...register("ssl_mode")} className="input">
                <option value="disable">Disable</option>
                <option value="allow">Allow</option>
                <option value="prefer">Prefer (recommended)</option>
                <option value="require">Require</option>
                <option value="verify-ca">Verify CA</option>
                <option value="verify-full">Verify Full</option>
              </select>
            </div>

            {/* Capability results */}
            {testResult && (
              <div className="card">
                <div className="card-header">
                  <span className="card-title">Capability check</span>
                  {testResult.server_version && (
                    <span className="mono-sm" style={{ color: "var(--text-3)" }}>
                      {testResult.server_version.split(" ").slice(0, 2).join(" ")}
                    </span>
                  )}
                </div>
                <div style={{ padding: "0 16px" }}>
                  {testResult.capabilities.map((c) => <CapRow key={c.name} check={c} />)}
                </div>
              </div>
            )}
          </div>

          <div className="dialog-footer">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={testMut.isPending}
              onClick={() => testMut.mutate(getValues() as ConnectionCreate)}
            >
              {testMut.isPending && <Loader2 size={13} className="spin" />}
              Test connection
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={saveMut.isPending}
              onClick={handleSubmit((d) => saveMut.mutate(d))}
            >
              {saveMut.isPending && <Loader2 size={13} className="spin" />}
              Save connection
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
