import { parsePrimitiveTree, type PrimitiveTree } from "@ze/ui";
import { PrimitiveTreeRenderer } from "@ze/ui/react";
import { usePrimitiveRendererActions } from "../api/usePrimitiveRendererActions";

export function ConnectedPrimitiveTree({ components }: { components: unknown }) {
  const actions = usePrimitiveRendererActions();

  let nodes: PrimitiveTree;
  try {
    nodes = parsePrimitiveTree(components);
  } catch {
    return null;
  }

  return <PrimitiveTreeRenderer nodes={nodes} actions={actions} />;
}
