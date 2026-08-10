import { getAccessToken } from "./api";

export type ChatEvent =
  | { event: "retrieval"; data: { chunk_count: number; denied_chunk_ids: string[]; timings: Record<string, number> } }
  | { event: "token"; data: { text: string; done: boolean } }
  | {
      event: "done";
      data: {
        grounded: boolean;
        abstained: boolean;
        citations: { index: number; document_id: string; chunk_id: string; title?: string; access_level?: string }[];
        latency_ms: number;
        rag_version: string | null;
        conversation_id?: string;
      };
    }
  | { event: "error"; data: { detail: string } };

/**
 * POST-based SSE client. The backend chat endpoint requires an auth header and
 * the request body, so a plain EventSource (GET only) won't work.
 */
export async function streamChat(
  body: { query: string; stream: boolean; model?: string; conversation_id?: string },
  onEvent: (e: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const resp = await fetch("/api/v1/chat/query", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${getAccessToken()}`,
    },
    body: JSON.stringify(body),
    signal,
  });
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const j = await resp.json();
      detail = j.detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  const reader = resp.body?.getReader();
  if (!reader) throw new Error("no response body");

  const decoder = new TextDecoder();
  let buffer = "";
  let eventName = "message";

  const flushLine = (line: string) => {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      try {
        onEvent({ event: eventName as ChatEvent["event"], data: JSON.parse(line.slice(5).trim()) });
      } catch {
        /* ignore malformed */
      }
    }
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        for (const line of block.split("\n")) flushLine(line);
      }
    }
    if (buffer.trim()) for (const line of buffer.split("\n")) flushLine(line);
  } finally {
    reader.releaseLock();
  }
}
