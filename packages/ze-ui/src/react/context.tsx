import { createContext, useContext } from "react";

export interface PrimitiveRendererActions {
  onButtonAction?: (action: string) => boolean | void;
  onFormSubmit?: (formId: string, values: Record<string, string>) => boolean | void;
  onDisconnected?: () => void;
}

const defaultActions: PrimitiveRendererActions = {};

export const PrimitiveRendererContext = createContext<PrimitiveRendererActions>(defaultActions);

export function usePrimitiveRendererActions(): PrimitiveRendererActions {
  return useContext(PrimitiveRendererContext);
}
