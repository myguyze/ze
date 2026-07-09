interface DashboardStatCardProps {
  label: string;
  value: string;
  hint?: string;
}

export function DashboardStatCard({ label, value, hint }: DashboardStatCardProps) {
  return (
    <div className="px-3 py-3 rounded-2xl bg-white/[0.03] border border-white/[0.06]">
      <p className="text-base font-light text-white tabular-nums">{value}</p>
      <p className="text-[10px] text-smoke mt-0.5">{label}</p>
      {hint && <p className="text-[9px] text-smoke/80 mt-0.5 truncate">{hint}</p>}
    </div>
  );
}
