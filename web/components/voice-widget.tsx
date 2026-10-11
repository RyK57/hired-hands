"use client";

import Script from "next/script";
import { createElement } from "react";

export function VoiceWidget({ agentId }: { agentId: string }) {
  return (
    <div className="flex min-h-24 items-center justify-center">
      {createElement("elevenlabs-convai", { "agent-id": agentId })}
      <Script src="https://unpkg.com/@elevenlabs/convai-widget-embed" strategy="afterInteractive" />
    </div>
  );
}
