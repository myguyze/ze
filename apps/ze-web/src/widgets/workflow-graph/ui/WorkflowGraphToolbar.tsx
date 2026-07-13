import { Maximize2, EyeOff, Eye } from "lucide-react";

interface Props {
  hideNotTaken: boolean;
  onToggleHideNotTaken: () => void;
  onFitView: () => void;
}

export function WorkflowGraphToolbar({ hideNotTaken, onToggleHideNotTaken, onFitView }: Props) {
  return (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-1 rounded-lg border border-white/10 bg-black/40 backdrop-blur-sm p-1">
        <button
          onClick={onFitView}
          className="p-1 rounded text-smoke hover:text-white transition-colors"
          title="Fit view"
        >
          <Maximize2 className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={onToggleHideNotTaken}
          className={`p-1 rounded transition-colors ${hideNotTaken ? "text-plum-voltage" : "text-smoke hover:text-white"}`}
          title={hideNotTaken ? "Show not-taken steps" : "Hide not-taken steps"}
        >
          {hideNotTaken ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
        </button>
      </div>
    </div>
  );
}
