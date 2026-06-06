import { CopilotSidebar } from "@copilotkit/react-ui";
import "@copilotkit/react-ui/styles.css";

export default function HomePage() {
  return (
    <CopilotSidebar
      defaultOpen
      labels={{
        title: "ArcGIS Documentation Guide",
        initial: "Hi! Ask me anything about ArcGIS Pro or ArcMap.",
      }}
    >
      <main className="mx-auto max-w-3xl px-6 py-16">
        <h1 className="text-3xl font-semibold tracking-tight">
          ArcGIS Documentation Guide
        </h1>
        <p className="mt-4 text-slate-600">
          Ask questions about ArcGIS Pro or ArcMap and get answers pulled
          directly from Esri's official documentation, with inline screenshots
          and source citations.
        </p>
        <p className="mt-2 text-sm text-slate-500">
          Use the chat panel on the right to get started.
        </p>
      </main>
    </CopilotSidebar>
  );
}
