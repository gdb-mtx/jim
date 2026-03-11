import { useEffect, useState } from "react";

export interface ToastMessage {
  id: number;
  text: string;
  type: "error" | "warning" | "info";
}

let nextId = 0;
let globalAdd: ((msg: Omit<ToastMessage, "id">) => void) | null = null;

/** Call from anywhere to show a toast. */
export function showToast(text: string, type: ToastMessage["type"] = "error") {
  globalAdd?.({ text, type });
}

const COLORS = {
  error: {
    bg: "bg-[#ff4d6a15]",
    border: "border-[#ff4d6a40]",
    text: "text-[#ff4d6a]",
  },
  warning: {
    bg: "bg-[#ffc04d15]",
    border: "border-[#ffc04d40]",
    text: "text-[#ffc04d]",
  },
  info: {
    bg: "bg-[#4d8eff15]",
    border: "border-[#4d8eff40]",
    text: "text-[#4d8eff]",
  },
};

export default function ToastContainer() {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  useEffect(() => {
    globalAdd = (msg) => {
      const id = nextId++;
      setToasts((prev) => [...prev, { ...msg, id }]);
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 6000);
    };
    return () => {
      globalAdd = null;
    };
  }, []);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((t) => {
        const c = COLORS[t.type];
        return (
          <div
            key={t.id}
            className={`rounded-lg border ${c.border} ${c.bg} px-4 py-3 text-sm ${c.text} shadow-lg animate-[fadeIn_0.2s_ease-out]`}
            style={{ maxWidth: 400 }}
          >
            <div className="flex items-start gap-2">
              <span className="flex-1">{t.text}</span>
              <button
                onClick={() =>
                  setToasts((prev) => prev.filter((x) => x.id !== t.id))
                }
                className="ml-2 opacity-60 hover:opacity-100"
              >
                x
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
