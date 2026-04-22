import React, { memo, useEffect, useState } from "react";
import { fetchOpsValidation } from "../../api";
import type {
  OpsValidationAccount,
  OpsValidationResponse,
} from "../../types";
import StatusDot, { type StatusTone } from "./StatusDot";

const STATUS_TONE: Record<string, StatusTone> = {
  pass: "green",
  marginal: "amber",
  fail: "red",
  retired: "gray",
  unvalidated: "red",
};

const STATUS_BADGE: Record<string, string> = {
  pass: "bg-[#00d4aa20] text-[#00d4aa]",
  marginal: "bg-[#ffc04d20] text-[#ffc04d]",
  fail: "bg-[#ff4d6a20] text-[#ff4d6a]",
  retired: "bg-[#8888a020] text-[#8888a0]",
  unvalidated: "bg-[#ff4d6a20] text-[#ff4d6a]",
};

function toneForAccount(a: OpsValidationAccount): StatusTone {
  // Retired is gray regardless of days_remaining — the account is out of the
  // rotation. Otherwise the status drives the primary tone; days_remaining
  // only flags an amber warning for near-expiry on PASS accounts.
  const tone = STATUS_TONE[a.status] ?? "gray";
  if (tone === "green" && a.days_remaining !== null && a.days_remaining < 30) {
    return "amber";
  }
  if (a.days_remaining !== null && a.days_remaining < 0 && a.status !== "retired") {
    return "red";
  }
  return tone;
}

function formatDaysRemaining(a: OpsValidationAccount): string {
  if (a.days_remaining === null) return "—";
  if (a.status === "retired") return `${a.days_remaining}d (retired)`;
  if (a.days_remaining < 0) return `expired ${-a.days_remaining}d ago`;
  return `${a.days_remaining}d`;
}

function formatPct(n: number | undefined, digits = 1): string {
  if (n === undefined) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}

export default memo(function ValidationPanel() {
  const [data, setData] = useState<OpsValidationResponse | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);

  useEffect(() => {
    const load = () => {
      fetchOpsValidation()
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
          Validation
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

      {data && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#2a2a3e] text-left text-xs font-medium tracking-wide text-[#8888a0] uppercase">
                <th className="pb-1.5 pr-3"></th>
                <th className="pb-1.5 pr-3">Account</th>
                <th className="pb-1.5 pr-3">Strategy</th>
                <th className="pb-1.5 pr-3">Status</th>
                <th className="pb-1.5 pr-3">Last run</th>
                <th className="pb-1.5 pr-3">Expires</th>
                <th className="pb-1.5 pr-3">Days</th>
                <th className="pb-1.5 pr-3">Report</th>
              </tr>
            </thead>
            <tbody>
              {data.accounts.map((a, i) => {
                const tone = toneForAccount(a);
                const isExpanded = expanded === i;
                return (
                  <React.Fragment key={a.account}>
                    <tr
                      className="border-b border-[#2a2a3e]/50 cursor-pointer hover:bg-[#2a2a3e20]"
                      onClick={() =>
                        setExpanded(isExpanded ? null : i)
                      }
                    >
                      <td className="py-2 pr-3">
                        <StatusDot tone={tone} />
                      </td>
                      <td className="py-2 pr-3 text-[#e8e8f0]">A{a.account}</td>
                      <td className="py-2 pr-3 text-[#c0c0d0]">{a.name}</td>
                      <td className="py-2 pr-3">
                        <span
                          className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                            STATUS_BADGE[a.status] ??
                            "bg-[#8888a020] text-[#8888a0]"
                          }`}
                        >
                          {a.status}
                        </span>
                      </td>
                      <td className="py-2 pr-3 text-[#c0c0d0] tabular-nums">
                        {a.last_run}
                      </td>
                      <td className="py-2 pr-3 text-[#c0c0d0] tabular-nums">
                        {a.expires}
                      </td>
                      <td
                        className={`py-2 pr-3 tabular-nums ${
                          tone === "red"
                            ? "text-[#ff4d6a]"
                            : tone === "amber"
                            ? "text-[#ffc04d]"
                            : "text-[#c0c0d0]"
                        }`}
                      >
                        {formatDaysRemaining(a)}
                      </td>
                      <td className="py-2 pr-3 text-xs text-[#4d8eff]">
                        {a.report_path ? (
                          <span>{a.report_path.split("/").pop()}</span>
                        ) : (
                          <span className="text-[#8888a0]">—</span>
                        )}
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr>
                        <td colSpan={8} className="px-3 pb-3 pt-1">
                          <div className="rounded-lg border border-[#2a2a3e] bg-[#12121a] p-3">
                            <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs md:grid-cols-4">
                              <div>
                                <div className="text-[#8888a0]">OOS CAGR</div>
                                <div className="tabular-nums text-[#e8e8f0]">
                                  {formatPct(a.oos_cagr)}
                                </div>
                              </div>
                              <div>
                                <div className="text-[#8888a0]">OOS MaxDD</div>
                                <div className="tabular-nums text-[#ff6b6b]">
                                  {formatPct(a.oos_maxdd)}
                                </div>
                              </div>
                              <div>
                                <div className="text-[#8888a0]">OOS Calmar</div>
                                <div className="tabular-nums text-[#e8e8f0]">
                                  {a.oos_calmar?.toFixed(2) ?? "—"}
                                </div>
                              </div>
                              <div>
                                <div className="text-[#8888a0]">OOS / IS</div>
                                <div className="tabular-nums text-[#e8e8f0]">
                                  {formatPct(a.oos_is_cagr_ratio, 0)}
                                </div>
                              </div>
                            </div>
                            {a.reason && (
                              <div className="mt-2 text-xs text-[#c0c0d0]">
                                <span className="text-[#8888a0]">Reason: </span>
                                {a.reason}
                              </div>
                            )}
                            {a.retired_reason && (
                              <div className="mt-1 text-xs text-[#c0c0d0]">
                                <span className="text-[#8888a0]">Retired: </span>
                                {a.retired_reason}
                              </div>
                            )}
                            {a.report_path && (
                              <div className="mt-2 text-xs text-[#8a8aa5]">
                                Report:{" "}
                                <code className="text-[#c0c0d0]">
                                  {a.report_path}
                                </code>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
});
