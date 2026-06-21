import { useState, type FormEvent } from "react";
import { cn } from "@/lib/cn";
import { send } from "@/features/websocket/useWebSocket";
import { useSendNotice } from "@/features/websocket/useSendNotice";
import { useOnboardingSession } from "@/features/onboarding/useOnboardingSession";
import { useSession } from "@/features/chat/hooks/useSession";
import type {
  Primitive,
  ColPrimitive,
  RowPrimitive,
  TextPrimitive,
  BadgePrimitive,
  SpacerPrimitive,
  ButtonPrimitive,
  ProgressPrimitive,
  TablePrimitive,
  FormPrimitive,
  ConnectionsPrimitive,
  ConnectionItem,
} from "./types";

// ── Gap / align helpers ───────────────────────────────────────────────────────

const GAP: Record<string, string> = {
  none: "gap-0",
  sm:   "gap-2",
  md:   "gap-4",
  lg:   "gap-6",
};

const ALIGN: Record<string, string> = {
  start:   "items-start",
  center:  "items-center",
  end:     "items-end",
  between: "justify-between items-center",
};

// ── Root renderer ─────────────────────────────────────────────────────────────

export function PrimitiveRenderer({ node }: { node: Primitive }) {
  switch (node.type) {
    case "col":         return <ColRenderer node={node} />;
    case "row":         return <RowRenderer node={node} />;
    case "text":        return <TextRenderer node={node} />;
    case "badge":       return <BadgeRenderer node={node} />;
    case "divider":     return <hr className="border-white/10 my-1" />;
    case "spacer":      return <SpacerRenderer node={node} />;
    case "button":      return <ButtonRenderer node={node} />;
    case "progress":    return <ProgressRenderer node={node} />;
    case "table":       return <TableRenderer node={node} />;
    case "form":        return <FormRenderer node={node} />;
    case "connections": return <ConnectionsRenderer node={node} />;
    default:
      // Unknown primitive from a newer backend — render nothing gracefully.
      return null;
  }
}

// ── Layout renderers ──────────────────────────────────────────────────────────

const COL_VARIANT: Record<string, string> = {
  default: "",
  card:    "mt-2 p-4 rounded-pill border border-white/10",
  section: "mt-2 p-4 rounded-pill border border-white/10 border-l-4 border-l-amber-spark",
};

function ColRenderer({ node }: { node: ColPrimitive }) {
  return (
    <div className={cn("flex flex-col", GAP[node.gap ?? "sm"], COL_VARIANT[node.variant ?? "default"])}>
      {node.children.map((child, i) => (
        <PrimitiveRenderer key={i} node={child} />
      ))}
    </div>
  );
}

function RowRenderer({ node }: { node: RowPrimitive }) {
  return (
    <div className={cn("flex flex-row flex-wrap", GAP[node.gap ?? "sm"], ALIGN[node.align ?? "start"])}>
      {node.children.map((child, i) => (
        <PrimitiveRenderer key={i} node={child} />
      ))}
    </div>
  );
}

// ── Content atom renderers ────────────────────────────────────────────────────

const TEXT_STYLE: Record<string, string> = {
  heading:    "text-[48px] font-extralight leading-none tracking-tight text-white",
  subheading: "text-sm font-semibold text-white",
  body:       "text-sm text-white",
  label:      "text-xs tracking-wide text-smoke",
  caption:    "text-xs text-ash",
  code:       "font-mono text-xs bg-white/5 rounded px-1 py-0.5 text-white",
};

const TEXT_COLOR: Record<string, string> = {
  default: "",
  muted:   "text-smoke",
  success: "text-lichen",
  warning: "text-amber-spark",
  error:   "text-red-400",
};

function TextRenderer({ node }: { node: TextPrimitive }) {
  const styleClass = TEXT_STYLE[node.style ?? "body"] ?? TEXT_STYLE.body;
  const colorClass = node.color && node.color !== "default" ? TEXT_COLOR[node.color] : "";
  return <p className={cn(styleClass, colorClass)}>{node.content}</p>;
}

const BADGE_COLOR: Record<string, string> = {
  default: "border-white/20 text-white",
  success: "border-lichen/50 text-lichen",
  warning: "border-amber-spark/50 text-amber-spark",
  error:   "border-red-400/50 text-red-400",
  info:    "border-plum-voltage/50 text-plum-voltage",
};

function BadgeRenderer({ node }: { node: BadgePrimitive }) {
  const colorClass = BADGE_COLOR[node.color ?? "default"] ?? BADGE_COLOR.default;
  return (
    <span className={cn("px-2 py-0.5 rounded-full border text-xs flex-shrink-0", colorClass)}>
      {node.label}
    </span>
  );
}

function SpacerRenderer({ node }: { node: SpacerPrimitive }) {
  const h = node.size === "lg" ? "h-6" : node.size === "sm" ? "h-1" : "h-3";
  return <div className={h} />;
}

function ButtonRenderer({ node }: { node: ButtonPrimitive }) {
  const threadId = useSession((s) => s.threadId);
  const notice = useSendNotice((s) => s.showNotice);
  const [used, setUsed] = useState(false);

  function handleClick() {
    if (used) return;
    const ok = send({ type: "message", text: node.action, thread_id: threadId });
    if (!ok) {
      notice("Not connected. Retry when Ze reconnects.");
      return;
    }
    setUsed(true);
  }

  const styleClass =
    node.style === "primary"
      ? "bg-plum-voltage text-white"
      : node.style === "danger"
        ? "border border-amber-spark text-amber-spark"
        : "border border-white/20 text-white";

  return (
    <button
      onClick={handleClick}
      disabled={used}
      className={cn(
        "px-4 py-2 rounded-pill text-xs font-semibold tracking-wide transition-opacity disabled:opacity-40",
        styleClass,
        used && "opacity-100",
      )}
    >
      {used ? `✓ ${node.label}` : node.label}
    </button>
  );
}

function ProgressRenderer({ node }: { node: ProgressPrimitive }) {
  const pct = Math.round(Math.max(0, Math.min(1, node.value)) * 100);
  return (
    <div className="w-full">
      {node.label && <p className="mb-1 text-xs text-smoke">{node.label}</p>}
      <div className="h-1.5 w-full rounded-full bg-white/10">
        <div
          className="h-1.5 rounded-full bg-plum-voltage transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ── Structured primitive renderers ────────────────────────────────────────────

function TableRenderer({ node }: { node: TablePrimitive }) {
  return (
    <div className="mt-2 overflow-auto max-h-72 rounded-pill border border-white/10">
      {node.title && (
        <p className="px-4 py-2 text-xs font-semibold tracking-widest uppercase text-smoke">
          {node.title}
        </p>
      )}
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-white/10">
            {node.headers.map((h) => (
              <th key={h} className="px-4 py-2 text-left text-xs font-semibold tracking-wide text-ash whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {node.rows.map((row, i) => (
            <tr key={i} className="border-b border-white/5 last:border-0">
              {row.map((cell, j) => (
                <td key={j} className="px-4 py-2 text-white/80 whitespace-nowrap">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {node.caption && (
        <p className="px-4 py-2 text-xs text-smoke">{node.caption}</p>
      )}
    </div>
  );
}

function FormRenderer({ node }: { node: FormPrimitive }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [submitted, setSubmitted] = useState(false);
  const sessionId = useOnboardingSession((s) => s.sessionId);
  const completed = useOnboardingSession((s) => s.completed);
  const threadId = useSession((s) => s.threadId);
  const notice = useSendNotice((s) => s.showNotice);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (submitted) return;
    setSubmitted(true);

    let sent = false;
    if (sessionId && !completed && node.id) {
      sent = send({ type: "component_submit", session_id: sessionId, step_id: node.id, values });
    } else if (node.id) {
      sent = send({ type: "component_submit", step_id: node.id, values, thread_id: threadId });
    } else {
      sent = send({ type: "message", text: `[form] ${JSON.stringify(values)}` });
    }

    if (!sent) {
      setSubmitted(false);
      notice("Not connected. Retry when Ze reconnects.");
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mt-2 p-4 rounded-pill border border-white/10 space-y-3">
      <p className="text-sm font-semibold text-white">{node.title}</p>
      {node.fields.map((field) => (
        <div key={field.id}>
          <label className="block text-xs text-smoke mb-1 tracking-wide">{field.label}</label>
          {field.field_type === "select" ? (
            <select
              value={values[field.id] ?? ""}
              onChange={(e) => setValues((v) => ({ ...v, [field.id]: e.target.value }))}
              disabled={submitted}
              className="w-full bg-transparent border border-white/20 rounded-pill px-3 py-2 text-sm text-white focus:outline-none focus:border-plum-voltage disabled:opacity-40"
            >
              <option value="">Select…</option>
              {field.options?.map((o) => (
                <option key={o} value={o} className="bg-black">{o}</option>
              ))}
            </select>
          ) : (
            <input
              type={field.field_type ?? "text"}
              placeholder={field.placeholder ?? undefined}
              value={values[field.id] ?? ""}
              onChange={(e) => setValues((v) => ({ ...v, [field.id]: e.target.value }))}
              disabled={submitted}
              className="w-full bg-transparent border border-white/20 rounded-pill px-3 py-2 text-sm text-white placeholder-smoke focus:outline-none focus:border-plum-voltage disabled:opacity-40"
            />
          )}
        </div>
      ))}
      <button
        type="submit"
        disabled={submitted}
        className="w-full py-2 rounded-pill bg-plum-voltage text-white text-xs font-semibold tracking-widest uppercase disabled:opacity-40 transition-opacity"
      >
        {submitted ? "Submitted" : "Submit"}
      </button>
    </form>
  );
}

const RELATION_LABELS: Record<string, string> = {
  pattern:      "Pattern",
  causal_guess: "Possible link",
  tension:      "Tension",
  convergence:  "Convergence",
};

function ConnectionCard({ item }: { item: ConnectionItem }) {
  const rel = RELATION_LABELS[item.relation] ?? item.relation;
  return (
    <div className="px-4 py-3 border-b border-white/5 last:border-0">
      <div className="flex items-start gap-2 mb-1">
        <span className="flex-shrink-0 mt-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium tracking-wide uppercase border border-plum-voltage/40 text-plum-voltage">
          {rel}
        </span>
        <p className="text-sm text-white leading-snug">{item.summary}</p>
      </div>
      <p className="text-xs text-smoke leading-relaxed mb-2">{item.narrative}</p>
      {item.evidence && item.evidence.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {item.evidence.map((ev, i) => (
            <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-white/5 text-[11px] text-smoke">
              {ev.label}
              {ev.date && <span className="text-white/30">· {ev.date}</span>}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function ConnectionsRenderer({ node }: { node: ConnectionsPrimitive }) {
  return (
    <div className="mt-2 rounded-pill border border-plum-voltage/20 overflow-hidden">
      <p className="px-4 py-2 text-xs font-semibold tracking-widest uppercase text-plum-voltage border-b border-plum-voltage/20">
        {node.title ?? "Connected to your history"}
      </p>
      {node.connections.map((item, i) => (
        <ConnectionCard key={i} item={item} />
      ))}
    </div>
  );
}
