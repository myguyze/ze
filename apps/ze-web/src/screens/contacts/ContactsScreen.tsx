import { useQuery } from "@tanstack/react-query";
import { Users } from "lucide-react";
import { api } from "@/lib/api";
import { FloatingButton } from "@/overlay/FloatingButton";

interface Contact {
  id: string;
  name: string;
  email?: string;
  notes?: string;
}

export function ContactsScreen() {
  const { data: contacts, isLoading } = useQuery({
    queryKey: ["contacts"],
    queryFn: () => api.get<Contact[]>("/api/contacts"),
  });

  return (
    <div className="px-4 py-8 space-y-6">
      <div>
        <p className="text-xs font-semibold tracking-widest uppercase text-[#9a9a9a] mb-1">
          Contacts
        </p>
        <p className="text-2xl font-extralight text-white">
          {contacts ? `${contacts.length} people` : "People"}
        </p>
      </div>

      {isLoading && (
        <div className="space-y-2">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-12 rounded-[24px] border border-white/10 animate-pulse" />
          ))}
        </div>
      )}

      {contacts?.length === 0 && (
        <div className="flex flex-col items-center py-16 gap-3">
          <Users className="w-8 h-8 text-[#9a9a9a]" />
          <p className="text-sm text-[#9a9a9a]">Ze will learn about people from your conversations.</p>
        </div>
      )}

      {contacts && contacts.length > 0 && (
        <div className="space-y-2">
          {contacts.map((c) => (
            <div key={c.id} className="flex items-center gap-3 p-3 rounded-[24px] border border-white/10 hover:border-white/20 transition-colors">
              <div className="w-8 h-8 rounded-full bg-[#8052ff]/20 flex items-center justify-center flex-shrink-0">
                <span className="text-xs text-[#8052ff] font-semibold">
                  {c.name[0]?.toUpperCase()}
                </span>
              </div>
              <div>
                <p className="text-sm text-white">{c.name}</p>
                {c.email && <p className="text-xs text-[#9a9a9a]">{c.email}</p>}
              </div>
            </div>
          ))}
        </div>
      )}

      <FloatingButton screen="contacts" />
    </div>
  );
}
