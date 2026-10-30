import { ToolCallAnnotator } from "@/components/tool-call-annotator";
import { DEMO_JOB } from "@/lib/mock-trajectory";

export const metadata = {
  title: "Annotate demo · Annocollector",
};

export default function AnnotateDemoPage() {
  return (
    <div className="flex h-screen flex-col">
      <ToolCallAnnotator job={DEMO_JOB} />
    </div>
  );
}
