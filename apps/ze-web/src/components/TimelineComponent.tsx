import { type TimelineComponent as T } from "./types";

export function TimelineComponent({ data }: { data: T }) {
  return (
    <div className="mt-2">
      {data.title && (
        <p className="mb-3 text-xs font-semibold tracking-widest uppercase text-[#9a9a9a]">
          {data.title}
        </p>
      )}
      <div className="space-y-0">
        {data.events.map((event, i) => (
          <div key={i} className="flex gap-4">
            <div className="flex flex-col items-center">
              <div className="w-1.5 h-1.5 mt-1.5 rounded-full bg-[#8052ff] flex-shrink-0" />
              {i < data.events.length - 1 && (
                <div className="w-px flex-1 mt-1 bg-white/10" />
              )}
            </div>
            <div className="pb-4">
              <p className="text-xs text-[#9a9a9a]">{event.time}</p>
              <p className="text-sm text-white mt-0.5">{event.title}</p>
              {event.description && (
                <p className="text-xs text-[#bdbdbd] mt-0.5">{event.description}</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
