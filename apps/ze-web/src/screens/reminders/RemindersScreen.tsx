import { useQuery } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { api } from "@/lib/api";
import { FloatingButton } from "@/overlay/FloatingButton";

interface Reminder {
  id: string;
  label: string;
  fire_at: string;
  fired: boolean;
}

export function RemindersScreen() {
  const { data: reminders, isLoading } = useQuery({
    queryKey: ["reminders"],
    queryFn: () => api.get<Reminder[]>("/api/reminders"),
  });

  const pending = reminders?.filter((r) => !r.fired) ?? [];
  const past = reminders?.filter((r) => r.fired) ?? [];

  return (
    <div className="px-4 py-8 space-y-6">
      <div>
        <p className="text-xs font-semibold tracking-widest uppercase text-[#9a9a9a] mb-1">
          Reminders
        </p>
        <p className="text-2xl font-extralight text-white">Upcoming</p>
      </div>

      {isLoading && (
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <div key={i} className="h-14 rounded-[24px] border border-white/10 animate-pulse" />
          ))}
        </div>
      )}

      {!isLoading && pending.length === 0 && (
        <div className="flex flex-col items-center py-16 gap-3">
          <Bell className="w-8 h-8 text-[#9a9a9a]" />
          <p className="text-sm text-[#9a9a9a]">No reminders. Ask Ze to set one.</p>
        </div>
      )}

      {pending.map((r) => (
        <div key={r.id} className="flex items-center justify-between p-4 rounded-[24px] border border-white/10">
          <p className="text-sm text-white">{r.label}</p>
          <p className="text-xs text-[#9a9a9a]">
            {new Date(r.fire_at).toLocaleString([], { dateStyle: "short", timeStyle: "short" })}
          </p>
        </div>
      ))}

      {past.length > 0 && (
        <div>
          <p className="text-xs text-[#9a9a9a] tracking-widest uppercase mb-3">Past</p>
          {past.slice(0, 5).map((r) => (
            <div key={r.id} className="flex items-center justify-between p-4 rounded-[24px] opacity-40">
              <p className="text-sm text-white line-through">{r.label}</p>
            </div>
          ))}
        </div>
      )}

      <FloatingButton screen="reminders" />
    </div>
  );
}
