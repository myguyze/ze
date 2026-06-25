import { Users } from "lucide-react";
import { FloatingButton } from "@/features/open-context-overlay";
import { ContactRow, useContactsQuery } from "@/entities/contact";
import { ListPage } from "@/shared/ui";

export function ContactsOverview() {
  const { data: contacts, isLoading, isError, refetch } = useContactsQuery();

  return (
    <>
      <ListPage
        label="Contacts"
        title={contacts ? `${contacts.length} people` : "People"}
        isLoading={isLoading}
        isError={isError}
        isEmpty={!contacts?.length}
        emptyIcon={Users}
        emptyMessage="Ze will learn about people from your conversations."
        errorMessage="Could not load contacts."
        onRetry={() => void refetch()}
        skeletonCount={4}
        skeletonHeight="h-12"
      >
        <div className="space-y-2">
          {contacts?.map((contact) => (
            <ContactRow key={contact.id} contact={contact} />
          ))}
        </div>
      </ListPage>

      <FloatingButton screen="contacts" />
    </>
  );
}
