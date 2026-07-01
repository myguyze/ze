import { Workflow } from "lucide-react";
import { FloatingButton } from "@/features/open-context-overlay";
import { useWorkflowsQuery, WorkflowCard } from "@/entities/workflow";
import { ListPage } from "@/shared/ui";

export function WorkflowsOverview() {
  const { data: workflows, isLoading, isError, refetch } = useWorkflowsQuery();

  return (
    <>
      <ListPage
        label="Automation"
        title="Workflows"
        isLoading={isLoading}
        isError={isError}
        isEmpty={!workflows?.length}
        emptyIcon={Workflow}
        emptyMessage="No workflows yet. Ask Ze to create one."
        errorMessage="Could not load workflows."
        onRetry={() => void refetch()}
      >
        <div className="space-y-4">
          {workflows?.map((workflow) => (
            <WorkflowCard key={workflow.id} workflow={workflow} />
          ))}
        </div>
      </ListPage>

      <FloatingButton screen="workflows" />
    </>
  );
}
