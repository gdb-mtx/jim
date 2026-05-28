import { memo, useEffect, useState } from "react";
import { fetchOpsScheduler } from "../../api";
import type {
  OpsSchedulerJob,
  OpsLaunchdEntry,
  OpsSchedulerResponse,
} from "../../types";
import StatusDot, { type StatusTone } from "./StatusDot";

function formatRelativeFuture(iso: string | null): string {
  if (!iso) return "—";
  const target = new Date(iso).getTime();
  if (isNaN(target)) return "—";
  const diffMs = target - Date.now();
  if (diffMs < 0) return "overdue";
  const mins = Math.round(diffMs / 60_000);
  if (mins < 60) return `in ${mins}m`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `in ${hours}h`;
  const days = Math.round(hours / 24);
  return `in ${days}d`;
}

function formatRelativePast(iso: string | null): string {
  if (!iso) return "never";
  const diffMs = Date.now() - new Date(iso).getTime();
  if (isNaN(diffMs) || diffMs < 0) return "just now";
  const mins = Math.round(diffMs / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

function toneForRebalanceJob(job: OpsSchedulerJob): StatusTone {
  if (job.last_status === "failed") return "red";
  // "partial" = orders submitted with ≥1 broker rejection (e.g. expected
  // sub-broker-minimum dust rejections — see CLAUDE.md). Same tone as
  // EventTimeline uses for `orders_failed > 0` so the two surfaces agree.
  if (job.last_status === "partial") return "amber";
  if (job.last_status === "skipped") return "amber";
  if (job.last_status === "running") return "blue";
  // success or null (never fired yet) both count as healthy — the job is
  // registered with launchd.
  return "green";
}

function toneForLaunchd(entry: OpsLaunchdEntry): StatusTone {
  if (!entry.last_run) return "gray";
  if (entry.outcome === "error") return "red";
  if (entry.outcome === "flip") return "purple";
  return "green";
}

function labelForStatus(status: OpsSchedulerJob["last_status"]): string {
  if (status === null) return "pending";
  return status;
}

export default memo(function SchedulerPanel() {
  const [data, setData] = useState<OpsSchedulerResponse | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);

  useEffect(() => {
    const load = () => {
      fetchOpsScheduler()
        .then((d) => {
          setData(d);
          setFetchError(null);
        })
        .catch((e) => setFetchError((e as Error).message));
    };
    load();
    const interval = setInterval(load, 30_000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium tracking-wide text-[#8888a0] uppercase">
          Schedulers
        </h2>
        {fetchError && (
          <span className="text-xs text-[#ff4d6a]">
            Fetch failed — {fetchError}
          </span>
        )}
      </div>

      {!data && !fetchError && (
        <p className="py-6 text-center text-sm text-[#8888a0] animate-pulse">
          Loading...
        </p>
      )}

      {data?.launchd_health && !data.launchd_health.ok && (
        <div className="mb-3 rounded-lg border border-[#ff4d6a40] bg-[#ff4d6a10] px-3 py-2">
          <div className="flex items-center gap-2 text-sm font-medium text-[#ff4d6a]">
            <span>⚠ macOS has disabled launchd agents</span>
          </div>
          {data.launchd_health.blocked?.map((b) => (
            <div key={b.label} className="mt-1 text-xs text-[#ff8899]">
              {b.label}: {b.reason}
            </div>
          ))}
          <div className="mt-1.5 text-xs text-[#8888a0]">
            Fix: launchctl unload / load the plist, or re-enable in System Settings → Login Items
          </div>
        </div>
      )}

      {data && (
        <div className="flex flex-col gap-4">
          {/* Daily rebalance — launchd-fired (replaced in-process APScheduler 2026-05-05) */}
          <div>
            <div className="mb-2 flex items-center gap-2">
              <span className="text-sm font-medium text-[#e8e8f0]">
                Scheduled rebalance (launchd)
              </span>
              <span className="text-xs text-[#8888a0]">
                runs even when the server is off
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#2a2a3e] text-left text-xs font-medium tracking-wide text-[#8888a0] uppercase">
                    <th className="pb-1.5 pr-3"></th>
                    <th className="pb-1.5 pr-3">Job</th>
                    <th className="pb-1.5 pr-3">Last run</th>
                    <th className="pb-1.5 pr-3">Next run</th>
                    <th className="pb-1.5 pr-3">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {data.scheduled_rebalance.jobs.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-2 text-[#8888a0]">
                        No jobs registered.
                      </td>
                    </tr>
                  ) : (
                    data.scheduled_rebalance.jobs.map((job) => {
                      const tone = toneForRebalanceJob(job);
                      return (
                        <tr
                          key={job.id}
                          className="border-b border-[#2a2a3e]/50 last:border-b-0"
                          title={job.error ?? undefined}
                        >
                          <td className="py-2 pr-3">
                            <StatusDot tone={tone} />
                          </td>
                          <td className="py-2 pr-3 text-[#e8e8f0]">
                            <div>{job.name}</div>
                            <div className="text-xs text-[#8888a0]">
                              {job.label ?? job.id}
                            </div>
                          </td>
                          <td className="py-2 pr-3 text-[#c0c0d0]">
                            {formatRelativePast(job.last_finished ?? job.last_started)}
                          </td>
                          <td className="py-2 pr-3 text-[#c0c0d0]">
                            {formatRelativeFuture(job.next_run_time)}
                          </td>
                          <td className="py-2 pr-3">
                            <span
                              className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                                tone === "green"
                                  ? "bg-[#00d4aa20] text-[#00d4aa]"
                                  : tone === "amber"
                                  ? "bg-[#ffc04d20] text-[#ffc04d]"
                                  : tone === "red"
                                  ? "bg-[#ff4d6a20] text-[#ff4d6a]"
                                  : tone === "blue"
                                  ? "bg-[#4d8eff20] text-[#4d8eff]"
                                  : "bg-[#8888a020] text-[#8888a0]"
                              }`}
                            >
                              {labelForStatus(job.last_status)}
                            </span>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* launchd — filter monitors (SPY + BTC every 4h) */}
          <div>
            <div className="mb-2 flex items-center gap-2">
              <span className="text-sm font-medium text-[#e8e8f0]">
                Filter monitors (launchd)
              </span>
              <span className="text-xs text-[#8888a0]">
                runs even when the server is off
              </span>
            </div>

            {data.launchd_error && (
              <p className="mb-2 text-xs text-[#ff4d6a]">
                {data.launchd_error}
              </p>
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#2a2a3e] text-left text-xs font-medium tracking-wide text-[#8888a0] uppercase">
                    <th className="pb-1.5 pr-3"></th>
                    <th className="pb-1.5 pr-3">Monitor</th>
                    <th className="pb-1.5 pr-3">Scope</th>
                    <th className="pb-1.5 pr-3">Last run</th>
                    <th className="pb-1.5 pr-3">Next run</th>
                    <th className="pb-1.5 pr-3">Outcome</th>
                    <th className="pb-1.5 pr-3">Flips</th>
                    <th
                      className="pb-1.5 pr-3 cursor-help"
                      title="Accounts rebalanced when this monitor's filter last flipped. Empty on no_change runs (most days) — only populates on flip events."
                    >
                      Accounts
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.launchd.map((entry) => {
                    const tone = toneForLaunchd(entry);
                    return (
                      <tr
                        key={entry.label}
                        className="border-b border-[#2a2a3e]/50 last:border-b-0"
                      >
                        <td className="py-2 pr-3">
                          <StatusDot tone={tone} />
                        </td>
                        <td className="py-2 pr-3">
                          <div className="text-[#e8e8f0]">{entry.label}</div>
                          <div className="text-xs text-[#8888a0]">
                            {entry.source}
                          </div>
                        </td>
                        <td className="py-2 pr-3 text-[#c0c0d0]">
                          {entry.scope ?? entry.expected_scope}
                        </td>
                        <td className="py-2 pr-3 text-[#c0c0d0]">
                          {entry.last_run_relative ?? "never"}
                        </td>
                        <td className="py-2 pr-3 text-[#c0c0d0]">
                          {formatRelativeFuture(entry.next_run)}
                        </td>
                        <td className="py-2 pr-3">
                          {entry.outcome ? (
                            <span
                              className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                                entry.outcome === "flip"
                                  ? "bg-[#7c4dff20] text-[#7c4dff]"
                                  : entry.outcome === "error"
                                  ? "bg-[#ff4d6a20] text-[#ff4d6a]"
                                  : entry.outcome === "first_run"
                                  ? "bg-[#4d8eff20] text-[#4d8eff]"
                                  : "bg-[#00d4aa20] text-[#00d4aa]"
                              }`}
                            >
                              {entry.outcome}
                            </span>
                          ) : (
                            <span className="text-xs text-[#8888a0]">—</span>
                          )}
                        </td>
                        <td className="py-2 pr-3 text-xs text-[#c0c0d0]">
                          {entry.flips.length === 0 ? (
                            <span className="text-[#8888a0]">—</span>
                          ) : (
                            entry.flips.map((f, i) => (
                              <span key={i} className="mr-2">
                                {f.filter.toUpperCase()} {f.from}→{f.to}
                              </span>
                            ))
                          )}
                        </td>
                        <td className="py-2 pr-3 text-xs text-[#c0c0d0]">
                          {entry.accounts.length === 0 ? (
                            <span className="text-[#8888a0]">—</span>
                          ) : (
                            entry.accounts
                              .map((a) => `A${a.account}:${a.status}`)
                              .join(", ")
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
});
