import { useState, type FormEvent } from "react";
import { cn } from "../lib/cn";
import type {
  Badge,
  Button,
  Col,
  ConnectionItem,
  Connections,
  Form,
  Primitive,
  ProgressBar,
  Row,
  Spacer,
  Table,
  Text,
} from "../generated/types.gen";
import {
  PrimitiveRendererContext,
  usePrimitiveRendererActions,
  type PrimitiveRendererActions,
} from "./context";

const GAP: Record<string, string> = {
  none: "gap-0",
  sm: "gap-2",
  md: "gap-4",
  lg: "gap-6",
};

const ALIGN: Record<string, string> = {
  start: "items-start",
  center: "items-center",
  end: "items-end",
  between: "justify-between items-center",
};

const COL_VARIANT: Record<string, string> = {
  default: "",
  card: "mt-2 p-4 rounded-pill border border-white/10",
  section: "mt-2 p-4 rounded-pill border border-white/10 border-l-4 border-l-amber-spark",
};

const TEXT_STYLE: Record<string, string> = {
  heading: "text-[48px] font-extralight leading-none tracking-tight text-white",
  subheading: "text-sm font-semibold text-white",
  body: "text-sm text-white",
  label: "text-xs tracking-wide text-smoke",
  caption: "text-xs text-ash",
  code: "font-mono text-xs bg-white/5 rounded px-1 py-0.5 text-white",
};

const TEXT_COLOR: Record<string, string> = {
  default: "",
  muted: "text-smoke",
  success: "text-lichen",
  warning: "text-amber-spark",
  error: "text-red-400",
};

const BADGE_COLOR: Record<string, string> = {
  default: "border-white/20 text-white",
  success: "border-lichen/50 text-lichen",
  warning: "border-amber-spark/50 text-amber-spark",
  error: "border-red-400/50 text-red-400",
  info: "border-plum-voltage/50 text-plum-voltage",
};

const RELATION_LABELS: Record<string, string> = {
  pattern: "Pattern",
  causal_guess: "Possible link",
  tension: "Tension",
  convergence: "Convergence",
};

export interface PrimitiveRendererProps {
  node: Primitive;
  actions?: PrimitiveRendererActions;
}

export function PrimitiveRenderer({ node, actions }: PrimitiveRendererProps) {
  const content = <PrimitiveNodeRenderer node={node} />;
  if (!actions) {
    return content;
  }
  return (
    <PrimitiveRendererContext.Provider value={actions}>
      {content}
    </PrimitiveRendererContext.Provider>
  );
}

export function PrimitiveTreeRenderer({
  nodes,
  actions,
}: {
  nodes: Primitive[];
  actions?: PrimitiveRendererActions;
}) {
  const tree = (
    <>
      {nodes.map((node, i) => (
        <PrimitiveNodeRenderer key={i} node={node} />
      ))}
    </>
  );

  if (!actions) {
    return tree;
  }

  return <PrimitiveRendererContext.Provider value={actions}>{tree}</PrimitiveRendererContext.Provider>;
}

function PrimitiveNodeRenderer({ node }: { node: Primitive }) {
  switch (node.type) {
    case "col":
      return <ColRenderer node={node} />;
    case "row":
      return <RowRenderer node={node} />;
    case "text":
      return <TextRenderer node={node} />;
    case "badge":
      return <BadgeRenderer node={node} />;
    case "divider":
      return <hr className="border-white/10 my-1" />;
    case "spacer":
      return <SpacerRenderer node={node} />;
    case "button":
      return <ButtonRenderer node={node} />;
    case "progress":
      return <ProgressRenderer node={node} />;
    case "table":
      return <TableRenderer node={node} />;
    case "form":
      return <FormRenderer node={node} />;
    case "connections":
      return <ConnectionsRenderer node={node} />;
    default: {
      const _exhaustive: never = node;
      return _exhaustive;
    }
  }
}

function ColRenderer({ node }: { node: Col }) {
  return (
    <div className={cn("flex flex-col", GAP[node.gap ?? "sm"], COL_VARIANT[node.variant ?? "default"])}>
      {node.children.map((child, i) => (
        <PrimitiveNodeRenderer key={i} node={child} />
      ))}
    </div>
  );
}

function RowRenderer({ node }: { node: Row }) {
  return (
    <div className={cn("flex flex-row flex-wrap", GAP[node.gap ?? "sm"], ALIGN[node.align ?? "start"])}>
      {node.children.map((child, i) => (
        <PrimitiveNodeRenderer key={i} node={child} />
      ))}
    </div>
  );
}

function TextRenderer({ node }: { node: Text }) {
  const styleClass = TEXT_STYLE[node.style ?? "body"] ?? TEXT_STYLE.body;
  const colorClass = node.color && node.color !== "default" ? TEXT_COLOR[node.color] : "";
  return <p className={cn(styleClass, colorClass)}>{node.content}</p>;
}

function BadgeRenderer({ node }: { node: Badge }) {
  const colorClass = BADGE_COLOR[node.color ?? "default"] ?? BADGE_COLOR.default;
  return (
    <span className={cn("px-2 py-0.5 rounded-full border text-xs flex-shrink-0", colorClass)}>
      {node.label}
    </span>
  );
}

function SpacerRenderer({ node }: { node: Spacer }) {
  const h = node.size === "lg" ? "h-6" : node.size === "sm" ? "h-1" : "h-3";
  return <div className={h} />;
}

function ButtonRenderer({ node }: { node: Button }) {
  const { onButtonAction, onDisconnected } = usePrimitiveRendererActions();
  const [used, setUsed] = useState(false);

  function handleClick() {
    if (used) return;
    const ok = onButtonAction?.(node.action);
    if (ok === false) {
      onDisconnected?.();
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
      type="button"
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

function ProgressRenderer({ node }: { node: ProgressBar }) {
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

function TableRenderer({ node }: { node: Table }) {
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
              <th
                key={h}
                className="px-4 py-2 text-left text-xs font-semibold tracking-wide text-ash whitespace-nowrap"
              >
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
      {node.caption && <p className="px-4 py-2 text-xs text-smoke">{node.caption}</p>}
    </div>
  );
}

function FormRenderer({ node }: { node: Form }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [submitted, setSubmitted] = useState(false);
  const { onFormSubmit, onDisconnected } = usePrimitiveRendererActions();

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (submitted) return;
    setSubmitted(true);

    const ok = onFormSubmit?.(node.id, values);
    if (ok === false) {
      setSubmitted(false);
      onDisconnected?.();
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
                <option key={o} value={o} className="bg-black">
                  {o}
                </option>
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
            <span
              key={i}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-white/5 text-[11px] text-smoke"
            >
              {ev.label}
              {ev.date && <span className="text-white/30">· {ev.date}</span>}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function ConnectionsRenderer({ node }: { node: Connections }) {
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
