import { useQuery } from "@tanstack/react-query";
import { listContacts } from "@ze/client";
import type { ContactListItem } from "@ze/client";
import { queryKeys } from "@/shared/lib";

export function useContactsQuery() {
  return useQuery<ContactListItem[]>({
    queryKey: queryKeys.contacts,
    queryFn: async () => {
      const { data } = await listContacts();
      return data ?? [];
    },
  });
}
