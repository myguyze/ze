import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

interface BreadcrumbCtx {
  detailTitle: string | null;
  setDetailTitle: (title: string | null) => void;
}

const BreadcrumbContext = createContext<BreadcrumbCtx>({
  detailTitle: null,
  setDetailTitle: () => {},
});

export function BreadcrumbProvider({ children }: { children: ReactNode }) {
  const [detailTitle, setDetailTitle] = useState<string | null>(null);
  return (
    <BreadcrumbContext.Provider value={{ detailTitle, setDetailTitle }}>
      {children}
    </BreadcrumbContext.Provider>
  );
}

export function useBreadcrumb() {
  return useContext(BreadcrumbContext);
}

export function useSetBreadcrumbTitle(title: string | null | undefined) {
  const { setDetailTitle } = useBreadcrumb();
  useEffect(() => {
    if (title) setDetailTitle(title);
    return () => setDetailTitle(null);
  }, [title, setDetailTitle]);
}
