import { useQuery } from "@tanstack/react-query";
import { Users } from "lucide-react";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/queryKeys";
import { type Contact } from "@/types/api";
import { FloatingButton } from "@/features/overlay/FloatingButton";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/layout/EmptyState";
import { ErrorState } from "@/components/layout/ErrorState";
import { ListSkeleton } from "@/components/layout/ListSkeleton";

export function ContactsPage() {
  const { data: contacts, isLoading, isError, refetch } = useQuery({
    queryKey: queryKeys.contacts,
    queryFn: () => api.get<Contact[]>("/api/contacts"),
  });

  return (
    <div className="px-4 py-8 space-y-6">
      <PageHeader
        label="Contacts"
        title={contacts ? `${contacts.length} people` : "People"}
      />

      {isLoading && <ListSkeleton count={4} height="h-12" />}

      {isError && (
        <ErrorState
          message="Could not load contacts."
          onRetry={() => void refetch()}
        />
      )}

      {!isError && contacts?.length === 0 && (
        <EmptyState
          icon={Users}
          message="Ze will learn about people from your conversations."
        />
      )}

      {!isError && contacts && contacts.length > 0 && (
        <div className="space-y-2">
          {contacts.map((c) => (
            <div key={c.id} className="flex items-center gap-3 p-3 rounded-pill border border-white/10 hover:border-white/20 transition-colors">
              <div className="w-8 h-8 rounded-full bg-plum-voltage/20 flex items-center justify-center flex-shrink-0">
                <span className="text-xs text-plum-voltage font-semibold">
                  {c.name[0]?.toUpperCase()}
                </span>
              </div>
              <div>
                <p className="text-sm text-white">{c.name}</p>
                {c.email && <p className="text-xs text-smoke">{c.email}</p>}
              </div>
            </div>
          ))}
        </div>
      )}

      <FloatingButton screen="contacts" />
    </div>
  );
}
