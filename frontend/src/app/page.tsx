"use client";

import { CopilotChat } from "@copilotkit/react-ui";
import "@copilotkit/react-ui/styles.css";
import { ChatSuggestions } from "@/components/ChatSuggestions";
import { markdownComponents } from "@/components/markdownComponents";

export default function HomePage() {
  return (
    <div className="flex flex-col h-screen">
      <header className="text-center pt-8 pb-4 px-6">
        <img
          src="https://www.esri.com/content/dam/esrisites/en-us/common/icons/esri-logo.svg"
          alt="Esri"
          className="h-10 mx-auto mb-4"
          onError={(e) => {
            e.currentTarget.style.display = "none";
          }}
        />
        <h1 className="text-2xl font-semibold tracking-tight">
          ArcGIS Documentation Guide
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          AI-powered Q&A for ArcGIS Pro and ArcMap documentation
        </p>
      </header>
      <CopilotChat
        className="flex-1 min-h-0"
        labels={{
          title: "ArcGIS Documentation Guide",
          initial: "Hi! Ask me anything about ArcGIS Pro or ArcMap.",
        }}
        markdownTagRenderers={markdownComponents}
      >
        <ChatSuggestions />
      </CopilotChat>
    </div>
  );
}
