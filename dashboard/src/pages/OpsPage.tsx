import SchedulerPanel from "../components/ops/SchedulerPanel";
import FilterStatePanel from "../components/ops/FilterStatePanel";
import ValidationPanel from "../components/ops/ValidationPanel";
import EventTimeline from "../components/ops/EventTimeline";

/**
 * Top-level Ops tab. Composes the four automation-status panels. No
 * account switcher — Ops is system-scoped, not per-account.
 *
 * Each panel polls its own endpoint at 30s cadence; failures are isolated
 * per panel via inline error state rather than a shared error boundary
 * so one broken endpoint doesn't blank the whole tab.
 */
export default function OpsPage() {
  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <SchedulerPanel />
        <FilterStatePanel />
      </div>
      <ValidationPanel />
      <EventTimeline />
    </div>
  );
}
