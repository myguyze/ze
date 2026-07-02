import { History, Route } from "lucide-react";
import { useChatSidePanelStore, type ChatSidePanelTab } from "@/features/chat-side-panel";
import { cn } from "@/shared/lib/cn";
import { TopBarQuickActionButton } from "@/shared/ui";

function SidePanelQuickAction({
  tab,
  label,
  icon: Icon,
}: {
  tab: ChatSidePanelTab;
  label: string;
  icon: typeof Route;
}) {
  const toggleTab = useChatSidePanelStore((s) => s.toggleTab);
  const open = useChatSidePanelStore((s) => s.open);
  const activeTab = useChatSidePanelStore((s) => s.tab);
  const active = open && activeTab === tab;

  return (
    <TopBarQuickActionButton
      onClick={() => toggleTab(tab)}
      title={active ? `Hide ${label}` : `Show ${label}`}
      aria-label={active ? `Hide ${label}` : `Show ${label}`}
      className={cn(active && "text-plum-voltage")}
    >
      <Icon className="w-3.5 h-3.5" />
      {label}
    </TopBarQuickActionButton>
  );
}

export function ChatSidePanelQuickActions() {
  return (
    <>
      <SidePanelQuickAction tab="trace" label="Trace" icon={Route} />
      <SidePanelQuickAction tab="history" label="History" icon={History} />
    </>
  );
}
