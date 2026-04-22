import { memo } from "react";

export type StatusTone = "green" | "amber" | "red" | "blue" | "purple" | "gray";

const TONE_HEX: Record<StatusTone, string> = {
  green: "#00d4aa",
  amber: "#ffc04d",
  red: "#ff4d6a",
  blue: "#4d8eff",
  purple: "#7c4dff",
  gray: "#8888a0",
};

/**
 * Shared colored dot used across Ops panels. Keeps the palette in one place so
 * new status states don't drift into novel colors that break the dashboard's
 * dark-theme tokens.
 */
export default memo(function StatusDot({
  tone,
  size = "sm",
}: {
  tone: StatusTone;
  size?: "sm" | "md";
}) {
  const dim = size === "md" ? "h-2.5 w-2.5" : "h-2 w-2";
  return (
    <span
      className={`inline-block rounded-full ${dim}`}
      style={{ backgroundColor: TONE_HEX[tone] }}
    />
  );
});

export { TONE_HEX };
