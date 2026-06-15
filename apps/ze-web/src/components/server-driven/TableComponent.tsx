import { type TableComponent as T } from "./types";

export function TableComponent({ data }: { data: T }) {
  return (
    <div className="mt-2 overflow-auto max-h-72 rounded-[24px] border border-white/10">
      {data.title && (
        <p className="px-4 py-2 text-xs font-semibold tracking-widest uppercase text-[#9a9a9a]">
          {data.title}
        </p>
      )}
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-white/10">
            {data.headers.map((h) => (
              <th
                key={h}
                className="px-4 py-2 text-left text-xs font-semibold tracking-wide text-[#bdbdbd] whitespace-nowrap"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.rows.map((row, i) => (
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
      {data.caption && (
        <p className="px-4 py-2 text-xs text-[#9a9a9a]">{data.caption}</p>
      )}
    </div>
  );
}
