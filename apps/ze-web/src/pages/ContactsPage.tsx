import { useQuery } from "@tanstack/react-query";
import { Users } from "lucide-react";
import { api } from "@/lib/api";
import { type Contact } from "@/types/api";
import { FloatingButton } from "@/features/overlay/FloatingButton";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/layout/EmptyState";
import { ListSkeleton } from "@/components/layout/ListSkeleton";

export function ContactsPage() {
  const { data: contacts, isLoading } = useQuery({
    queryKey: ["contacts"],
    queryFn: () => api.get<Contact[]>("/api/contacts"),
  });

  return (
    <div className="px-4 py-8 space-y-6">
      <PageHeader
        label="Contacts"
        title={contacts ? `${contacts.length} people` : "People"}
      />

      {isLoading && <ListSkeleton count={4} height="h-12" />}

      {contacts?.length === 0 && (
        <EmptyState
          icon={Users}
          message="Ze will learn about people from your conversations."
        />
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
