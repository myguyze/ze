interface PageHeaderProps {
  label: string;
  title: string;
}

export function PageHeader({ label, title }: PageHeaderProps) {
  return (
    <div>
      <p className="text-xs font-semibold tracking-widest uppercase text-[#9a9a9a] mb-1">
        {label}
      </p>
      <p className="text-2xl font-extralight text-white">{title}</p>
    </div>
  );
}
