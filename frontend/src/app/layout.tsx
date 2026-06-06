import type { ReactNode } from "react";
import { CopilotKit } from "@copilotkit/react-core";
import "./globals.css";

export const metadata = {
  title: "ArcGIS Documentation Guide",
  description: "AI-powered chat for ArcGIS Pro and ArcMap documentation",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">
        <CopilotKit runtimeUrl="/api/copilotkit">
          {children}
        </CopilotKit>
      </body>
    </html>
  );
}
