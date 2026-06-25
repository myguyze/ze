import type { ContactListItem } from "@ze/client";

export function ContactRow({ contact }: { contact: ContactListItem }) {
  return (
    <div className="flex items-center gap-3 p-3 rounded-pill border border-white/10 hover:border-white/20 transition-colors">
      <div className="w-8 h-8 rounded-full bg-plum-voltage/20 flex items-center justify-center flex-shrink-0">
        <span className="text-xs text-plum-voltage font-semibold">
          {contact.name[0]?.toUpperCase()}
        </span>
      </div>
      <div>
        <p className="text-sm text-white">{contact.name}</p>
        {contact.email && <p className="text-xs text-smoke">{contact.email}</p>}
      </div>
    </div>
  );
}
