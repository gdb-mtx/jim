import type { ReactNode } from "react";

interface Props {
  text: string;
  children: ReactNode;
}

export default function Tooltip({ text, children }: Props) {
  return (
    <div className="group/tip relative inline-flex">
      {children}
      <div
        className="pointer-events-none absolute left-full top-1/2 z-50 ml-2 -translate-y-1/2
          max-w-[480px] whitespace-pre rounded-lg border border-[#2a2a3e] bg-[#1a1a2e] px-3 py-2
          text-xs leading-relaxed text-[#c8c8d8] shadow-lg font-mono
          invisible opacity-0 transition-opacity duration-150
          group-hover/tip:visible group-hover/tip:opacity-100"
      >
        {text}
      </div>
    </div>
  );
}
