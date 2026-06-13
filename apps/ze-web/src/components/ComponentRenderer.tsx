import { type ComponentDescriptor } from "./types";
import { TableComponent } from "./TableComponent";
import { MetricComponent } from "./MetricComponent";
import { ListComponent } from "./ListComponent";
import { TimelineComponent } from "./TimelineComponent";
import { ProgressComponent } from "./ProgressComponent";
import { ConfirmComponent } from "./ConfirmComponent";
import { FormComponent } from "./FormComponent";
import { CardComponent } from "./CardComponent";

export function ComponentRenderer({ data }: { data: ComponentDescriptor }) {
  try {
    switch (data.type) {
      case "table":    return <TableComponent data={data} />;
      case "metric":   return <MetricComponent data={data} />;
      case "list":     return <ListComponent data={data} />;
      case "timeline": return <TimelineComponent data={data} />;
      case "progress": return <ProgressComponent data={data} />;
      case "confirm":  return <ConfirmComponent data={data} />;
      case "form":     return <FormComponent data={data} />;
      case "card":     return <CardComponent data={data} />;
    }
  } catch {
    return null;
  }
}
