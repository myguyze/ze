import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

interface TopBarActionsCtx {
  quickActions: ReactNode;
  setQuickActions: (actions: ReactNode) => void;
}

const TopBarActionsContext = createContext<TopBarActionsCtx>({
  quickActions: null,
  setQuickActions: () => {},
});

export function TopBarActionsProvider({ children }: { children: ReactNode }) {
  const [quickActions, setQuickActions] = useState<ReactNode>(null);
  return (
    <TopBarActionsContext.Provider value={{ quickActions, setQuickActions }}>
      {children}
    </TopBarActionsContext.Provider>
  );
}

export function useTopBarActions() {
  return useContext(TopBarActionsContext);
}

/** Register optional quick actions for the current screen. Cleared on unmount. */
export function useTopBarQuickActions(actions: ReactNode) {
  const { setQuickActions } = useTopBarActions();
  useEffect(() => {
    setQuickActions(actions);
    return () => setQuickActions(null);
  }, [actions, setQuickActions]);
}
