import { useParams } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2, Play, TrendingDown, Layers } from "lucide-react";
import { api } from "@/api/client";
import { formatBytes, cn } from "@/lib/utils";

function CostDiff({ before, after }: { before: number; after: number }) {
  const reduction = ((before - after) / before) * 100;
  const positive = after < before;
  return (
    <div className="flex items-center gap-3">
      <div className="text-right">
        <p className="text-[10px] text-muted-foreground">Before</p>
        <p className="text-base font-bold text-foreground">{before.toFixed(1)}</p>
      </div>
      <div className={cn("flex flex-col items-center px-2", positive ? "text-emerald-400" : "text-red-400")}>
        <TrendingDown className="h-4 w-4" />
        <p className="text-[10px] font-semibold">{positive ? "-" : "+"}{Math.abs(reduction).toFixed(1)}%</p>
      </div>
      <div>
        <p className="text-[10px] text-muted-foreground">After</p>
        <p className={cn("text-base font-bold", positive ? "text-emerald-400" : "text-foreground")}>
          {after.toFixed(1)}
        </p>
      </div>
    </div>
  );
}

export function ExperimentPage() {
  const { experimentId } = useParams<{
    experimentId: string;
  }>();

  const { data: experiment, isLoading } = useQuery({
    queryKey: ["experiment", experimentId],
    queryFn: () => api.experiments.get(experimentId!),
    enabled: !!experimentId,
    refetchInterval: (data) =>
      data?.state?.data?.status === "running" ? 2000 : false,
  });

  const runMutation = useMutation({
    mutationFn: () => api.experiments.run(experimentId!),
    onSuccess: () => toast.success("Experiment started"),
    onError: (e: Error) => toast.error(e.message),
  });

  if (isLoading) return <div className="p-8"><div className="h-96 rounded-xl shimmer" /></div>;
  if (!experiment) return <div className="p-8 text-muted-foreground">Experiment not found.</div>;

  const diff = experiment.plan_diff;
  const isPending = experiment.status === "pending";
  const isRunning = experiment.status === "running";
  const isComplete = experiment.status === "complete";

  return (
    <div className="p-8 animate-fade-in max-w-5xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <p className="text-xs text-muted-foreground uppercase tracking-widest mb-1">Experiment</p>
          <h1 className="text-xl font-bold text-foreground">Plan Comparison</h1>
        </div>
        <div className="flex items-center gap-3">
          {!experiment.hypopg_available && (
            <span className="badge-review rounded-full px-2.5 py-0.5 text-[10px]">
              HypoPG unavailable — lower confidence
            </span>
          )}
          {(isPending || isComplete) && (
            <button
              onClick={() => runMutation.mutate()}
              disabled={runMutation.isPending || isRunning}
              className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-all disabled:opacity-50"
            >
              {runMutation.isPending || isRunning
                ? <Loader2 className="h-4 w-4 animate-spin" />
                : <Play className="h-4 w-4" />}
              {isComplete ? "Run Again" : "Run Experiment"}
            </button>
          )}
        </div>
      </div>

      {/* Status banner */}
      {isRunning && (
        <div className="flex items-center gap-3 rounded-lg border border-primary/25 bg-primary/8 px-4 py-3 mb-6">
          <Loader2 className="h-4 w-4 text-primary animate-spin" />
          <p className="text-sm text-primary">Experiment running — fetching hypothetical plan…</p>
        </div>
      )}

      {/* Summary cards */}
      {isComplete && diff && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
          {/* Cost */}
          <div className="metric-card">
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2">Planner Cost</p>
            {diff.cost && (
              <CostDiff before={diff.cost.before} after={diff.cost.after} />
            )}
          </div>

          {/* Scan type */}
          <div className="metric-card">
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2">Scan Type</p>
            {diff.scan_change ? (
              <div>
                <p className="text-xs">
                  <span className={cn("rounded px-1.5 py-0.5 text-[10px]",
                    diff.scan_change.before.includes("Seq") ? "node-seq-scan" : "node-index-scan")}>
                    {diff.scan_change.before}
                  </span>
                  {" → "}
                  <span className={cn("rounded px-1.5 py-0.5 text-[10px]",
                    diff.scan_change.after.includes("Index") ? "node-index-scan" : "node-seq-scan")}>
                    {diff.scan_change.after}
                  </span>
                </p>
                {diff.scan_change.before !== diff.scan_change.after && (
                  <p className="text-[10px] text-emerald-400 mt-1">✓ Plan changed</p>
                )}
              </div>
            ) : <p className="text-sm text-muted-foreground">No change</p>}
          </div>

          {/* Sort nodes */}
          <div className="metric-card">
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2">Sort Nodes</p>
            {diff.sort && (
              <div className="flex items-center gap-2">
                <span className="text-lg font-bold text-foreground">{diff.sort.before}</span>
                <span className="text-muted-foreground">→</span>
                <span className={cn("text-lg font-bold",
                  diff.sort.after < diff.sort.before ? "text-emerald-400" : "text-foreground")}>
                  {diff.sort.after}
                </span>
                {diff.sort.before > diff.sort.after && (
                  <span className="text-[10px] text-emerald-400">Sort removed!</span>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Storage estimate */}
      {experiment.storage_estimate_bytes && (
        <div className="flex items-center gap-3 rounded-lg border border-white/8 bg-secondary/20 px-4 py-3 mb-4">
          <Layers className="h-4 w-4 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            Estimated index size: <span className="text-foreground font-medium">
              {formatBytes(experiment.storage_estimate_bytes)}
            </span>
          </p>
        </div>
      )}

      {/* Before / After plan split */}
      {isComplete && (
        <div className="grid grid-cols-2 gap-4">
          <div className="glass-card rounded-xl">
            <div className="px-4 py-2.5 border-b border-white/8">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-widest">Before Plan</p>
            </div>
            <pre className="p-4 text-[10px] font-mono text-foreground/70 overflow-x-auto scrollbar-thin max-h-64">
              {JSON.stringify(experiment.before_plan_json, null, 2)}
            </pre>
          </div>
          <div className="glass-card rounded-xl border border-emerald-500/20">
            <div className="px-4 py-2.5 border-b border-white/8">
              <p className="text-xs font-semibold text-emerald-400 uppercase tracking-widest">
                Hypothetical Plan {experiment.hypopg_available ? "" : "(no HypoPG)"}
              </p>
            </div>
            <pre className="p-4 text-[10px] font-mono text-foreground/70 overflow-x-auto scrollbar-thin max-h-64">
              {JSON.stringify(experiment.after_plan_json, null, 2)}
            </pre>
          </div>
        </div>
      )}

      {/* Error state */}
      {experiment.status === "failed" && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4">
          <p className="text-sm font-medium text-destructive">{experiment.error_code}</p>
          <p className="text-xs text-destructive/70 mt-1">{experiment.error_message}</p>
        </div>
      )}
    </div>
  );
}
