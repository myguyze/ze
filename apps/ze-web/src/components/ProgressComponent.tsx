import { motion } from "framer-motion";
import { type ProgressComponent as T } from "./types";

export function ProgressComponent({ data }: { data: T }) {
  return (
    <div className="mt-2">
      <p className="mb-3 text-sm font-semibold text-white">{data.title}</p>
      <div className="space-y-0">
        {data.steps.map((step, i) => (
          <div key={i} className="flex gap-3">
            <div className="flex flex-col items-center">
              {step.status === "done" && (
                <div className="w-4 h-4 mt-0.5 rounded-full bg-[#8052ff] flex-shrink-0 flex items-center justify-center">
                  <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 10 10">
                    <path d="M2 5l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
              )}
              {step.status === "active" && (
                <motion.div
                  className="w-4 h-4 mt-0.5 rounded-full border-2 border-[#8052ff] flex-shrink-0"
                  animate={{ opacity: [1, 0.3, 1] }}
                  transition={{ duration: 1.5, repeat: Infinity }}
                />
              )}
              {step.status === "pending" && (
                <div className="w-4 h-4 mt-0.5 rounded-full border border-white/20 flex-shrink-0" />
              )}
              {i < data.steps.length - 1 && (
                <div className="w-px flex-1 mt-1 mb-1 bg-white/10" />
              )}
            </div>
            <p
              className={`pb-4 text-sm leading-5 ${
                step.status === "done"
                  ? "text-[#9a9a9a] line-through"
                  : step.status === "active"
                    ? "text-white"
                    : "text-[#9a9a9a]"
              }`}
            >
              {step.label}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
