import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { useAuth } from "../context/AuthContext";
import { streamChat } from "../lib/sse";
import { chatApi, errMsg } from "../lib/api";
import type { ConversationSummary, MessageSummary } from "../lib/types";
import { Badge, Spinner } from "../components/ui";

type Citation = { index?: number; document_id: string; chunk_id?: string; title?: string; access_level?: string };

interface UiMessage {
  role: "user" | "assistant" | "error";
  content: string;
  citations?: Citation[];
  grounded?: boolean;
  abstained?: boolean;
  latency?: number;
  conversationId?: string;
  streaming?: boolean;
}

export default function Chat() {
  const { identity } = useAuth();
  const [convs, setConvs] = useState<ConversationSummary[]>([]);
  const [activeConv, setActiveConv] = useState<string | null>(null);
  const [convLoaded, setConvLoaded] = useState(false);
  const [ui, setUi] = useState<UiMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const loadConversations = async () => {
    try {
      setConvs(await chatApi.conversations());
    } catch (e) {
      setError(errMsg(e));
    }
  };

  useEffect(() => {
    loadConversations();
  }, []);

  useEffect(() => {
    if (activeConv && !convLoaded) {
      chatApi
        .messages(activeConv)
        .then((ms: MessageSummary[]) => {
          setUi(ms.map((m) => ({ role: m.role as UiMessage["role"], content: m.content })));
          setConvLoaded(true);
        })
        .catch((e) => setError(errMsg(e)));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeConv, convLoaded]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [ui]);

  const newConversation = () => {
    abortRef.current?.abort();
    setActiveConv(null);
    setConvLoaded(false);
    setUi([]);
    setError("");
  };

  const send = async () => {
    const q = input.trim();
    if (!q || busy) return;
    setInput("");
    setError("");
    setUi((u) => [...u, { role: "user", content: q }, { role: "assistant", content: "", streaming: true }]);
    setBusy(true);
    const ac = new AbortController();
    abortRef.current = ac;

    let convId = activeConv;

    try {
      await streamChat(
        { query: q, stream: true, conversation_id: convId ?? undefined },
        (ev) => {
          if (ev.event === "token") {
            setUi((u) => {
              const copy = [...u];
              const last = copy[copy.length - 1];
              copy[copy.length - 1] = { ...last, content: last.content + ev.data.text };
              return copy;
            });
          } else if (ev.event === "done") {
            convId = ev.data.conversation_id ?? convId;
            setUi((u) => {
              const copy = [...u];
              const last = copy[copy.length - 1];
              copy[copy.length - 1] = {
                ...last,
                citations: ev.data.citations,
                grounded: ev.data.grounded,
                abstained: ev.data.abstained,
                latency: ev.data.latency_ms,
                conversationId: ev.data.conversation_id,
                streaming: false,
              };
              return copy;
            });
            setActiveConv(convId);
            setConvLoaded(true);
            loadConversations();
          } else if (ev.event === "error") {
            setUi((u) => {
              const copy = [...u];
              copy[copy.length - 1] = {
                role: "error",
                content: ev.data.detail,
                streaming: false,
              };
              return copy;
            });
          }
        },
        ac.signal,
      );
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        setUi((u) => {
          const copy = [...u];
          copy[copy.length - 1] = { role: "error", content: errMsg(e), streaming: false };
          return copy;
        });
      }
    } finally {
      setBusy(false);
    }
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const stop = () => {
    abortRef.current?.abort();
    setBusy(false);
  };

  return (
    <div className="chat-page">
      <div className="row-between mb">
        <div>
          <h1 style={{ margin: 0 }}>Chat</h1>
          <div className="sub muted">Ask questions against your tenant's documents.</div>
        </div>
        <div className="row">
          {busy && (
            <button className="btn danger sm" onClick={stop}>
              Stop
            </button>
          )}
          <button className="btn" onClick={newConversation}>
            + New
          </button>
        </div>
      </div>
      {error && <div className="error-box">{error}</div>}
      <div className="chat-tabs">
        {convs.map((c) => (
          <button
            key={c.id}
            className={`btn sm ${c.id === activeConv ? "primary" : ""}`}
            onClick={() => {
              setActiveConv(c.id);
              setConvLoaded(false);
            }}
          >
            {c.title}
          </button>
        ))}
        {convs.length === 0 && <span className="muted">No conversations yet</span>}
      </div>
      <div className="chat-main">
        {ui.length === 0 && (
          <div className="empty">
            Ask a question below — RAGShield will retrieve only documents you're authorized to see
            {identity ? ` (tenant ${identity.tenant_id.slice(0, 8)})` : ""}.
          </div>
        )}
        {ui.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.content}
            {m.streaming && <span className="spinner" style={{ marginLeft: 8 }} />}
            {(m.citations ?? []).map((c) => (
              <div key={c.document_id + (c.chunk_id ?? "")} className="citation-wrap">
                <span className="citation">
                  <b>{c.index ?? "?"}</b> · {c.title ?? c.document_id.slice(0, 12)}
                </span>
              </div>
            ))}
            {(m.grounded !== undefined || m.latency) && (
              <div className="msg-meta">
                {m.grounded !== undefined && (
                  <Badge tone={m.abstained ? "amber" : m.grounded ? "green" : "red"}>
                    {m.abstained ? "abstained" : m.grounded ? "grounded" : "ungrounded"}
                  </Badge>
                )}
                {m.latency && <span>{m.latency}ms</span>}
              </div>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <div className="chat-input-row">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKey}
          placeholder="Ask about your documents… (Enter to send)"
          disabled={busy}
        />
        <button className="btn primary" onClick={send} disabled={busy || !input.trim()}>
          {busy ? <Spinner /> : (
            <>
              Send
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="m22 2-7 20-4-9-9-4z" />
                <path d="M22 2 11 13" />
              </svg>
            </>
          )}
        </button>
      </div>
    </div>
  );
}
