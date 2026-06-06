"use client";

import { useCopilotChatSuggestions } from "@copilotkit/react-core";

const SUGGESTIONS = [
  {
    title: "Buffer in ArcGIS Pro",
    message: "How do I create a buffer in ArcGIS Pro?",
  },
  {
    title: "Geodatabase basics",
    message: "What is a geodatabase?",
  },
  {
    title: "Export map to PDF",
    message: "How to export a map to PDF?",
  },
  {
    title: "Georeference in ArcMap",
    message: "How do I georeference in ArcMap?",
  },
  {
    title: "Clip vs Intersect",
    message: "What's the difference between Clip and Intersect?",
  },
  {
    title: "ArcPy batch processing",
    message: "How to use ArcPy for batch processing?",
  },
];

export const ChatSuggestions: React.FC = () => {
  useCopilotChatSuggestions({
    suggestions: SUGGESTIONS,
    available: "before-first-message",
  });
  return null;
};
