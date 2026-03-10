interface Props {
  label: string;
  value: string;
  subtext?: string;
  color?: "green" | "red" | "blue" | "yellow" | "default";
}

const colorMap = {
  green: "text-[#00d4aa]",
  red: "text-[#ff4d6a]",
  blue: "text-[#4d8eff]",
  yellow: "text-[#ffc04d]",
  default: "text-[#e8e8f0]",
};

export default function MetricCard({ label, value, subtext, color = "default" }: Props) {
  return (
    <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
      <p className="text-xs font-medium tracking-wide text-[#8888a0] uppercase">
        {label}
      </p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${colorMap[color]}`}>
        {value}
      </p>
      {subtext && (
        <p className="mt-1 text-xs text-[#8888a0]">{subtext}</p>
      )}
    </div>
  );
}
