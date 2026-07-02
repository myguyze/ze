import { useQuery } from "@tanstack/react-query";
import { listDataDomains } from "@myguyze/ze-client";
import type { DataDomainsResponse } from "@myguyze/ze-client";
import { queryKeys } from "@/shared/lib";

export function useDataDomainsQuery() {
  return useQuery<DataDomainsResponse>({
    queryKey: queryKeys.dataDomains(),
    queryFn: async () => {
      const { data } = await listDataDomains();
      return data!;
    },
  });
}
