import { useEffect, useRef, useState } from 'react';

interface ChatMessage {
  id: number;
  role: 'user' | 'ai' | 'error';
  text: string;
  /** Summary bubbles: citations stripped from the text, shown on demand. */
  summary?: boolean;
  citations?: string[];
  provider?: string;
  fallbackReason?: string | null;
}

// Trailing citations like "[snapshot=<hex>; path=/json/pointer]".
const CITATION_RE = / ?\[snapshot=[0-9a-fA-F]+;\s*path=[^\]\n]*\]/g;

function stripCitations(text: string): { body: string; citations: string[] } {
  const citations = (text.match(CITATION_RE) ?? []).map((c) =>
    c.trim().replace(/^\[/, '').replace(/\]$/, ''),
  );
  const body = text.replace(CITATION_RE, '').trim();
  return { body, citations };
}

interface SummaryResponse {
  summary: string;
  provider: string;
  fallback_reason: string | null;
}

/** Free-form chat is served by the backend; no browser-side key needed. */
async function callBackendChat(history: ChatMessage[]): Promise<string> {
  // Map to the API contract (user/model roles). Error bubbles are excluded;
  // consecutive same-role messages are merged to keep the turns alternating.
  const messages: Array<{ role: 'user' | 'model'; text: string }> = [];
  for (const m of history) {
    if (m.role === 'error') continue;
    const role = m.role === 'user' ? ('user' as const) : ('model' as const);
    const last = messages[messages.length - 1];
    if (last && last.role === role) {
      last.text += `\n${m.text}`;
    } else {
      messages.push({ role, text: m.text });
    }
  }

  let resp: Response;
  try {
    resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages }),
    });
  } catch {
    throw new Error('Network error: could not reach the backend.');
  }
  const data: unknown = await resp.json().catch(() => null);
  if (!resp.ok) {
    const detail =
      data && typeof data === 'object' && 'detail' in data && typeof data.detail === 'string'
        ? data.detail
        : `HTTP ${resp.status}`;
    throw new Error(detail);
  }
  const reply = (data as { reply?: unknown }).reply;
  if (typeof reply !== 'string' || !reply.trim()) {
    throw new Error('Backend returned an empty reply.');
  }
  return reply;
}

export default function ChatPanel() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [typing, setTyping] = useState(false);
  const [summaryTyping, setSummaryTyping] = useState<false | 'template' | 'gemini'>(false);
  const [openCitations, setOpenCitations] = useState<Set<number>>(new Set());
  const listRef = useRef<HTMLDivElement>(null);
  const nextId = useRef(1);
  const alive = useRef(true);

  // Keep the message list pinned to the bottom as content arrives.
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, typing, summaryTyping]);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const pushMessage = (msg: Omit<ChatMessage, 'id'>) => {
    if (!alive.current) return;
    setMessages((m) => [...m, { ...msg, id: nextId.current++ }]);
  };

  const send = async () => {
    const text = draft.trim();
    if (!text || typing) return;
    const userMsg: ChatMessage = { id: nextId.current++, role: 'user', text };
    const history = [...messages, userMsg];
    setMessages(history);
    setDraft('');
    setTyping(true);
    try {
      const reply = await callBackendChat(history);
      pushMessage({ role: 'ai', text: reply });
    } catch (e) {
      pushMessage({
        role: 'error',
        text: e instanceof Error ? e.message : 'Chat request failed.',
      });
    } finally {
      if (alive.current) setTyping(false);
    }
  };

  // Server-side trading-flow summary; the result lands in the message flow as
  // a dismissible summary bubble.
  const summarize = async (ai: boolean) => {
    if (summaryTyping) return;
    setSummaryTyping(ai ? 'gemini' : 'template');
    try {
      const resp = await fetch(`/api/analytics/summary?ai=${ai}`, { method: 'POST' });
      const data: unknown = await resp.json().catch(() => null);
      if (!resp.ok) {
        const detail =
          data && typeof data === 'object' && 'detail' in data && typeof data.detail === 'string'
            ? data.detail
            : `HTTP ${resp.status}`;
        throw new Error(detail);
      }
      const s = data as SummaryResponse;
      const { body, citations } = stripCitations(s.summary);
      pushMessage({
        role: 'ai',
        text: body,
        summary: true,
        citations,
        provider: s.provider,
        fallbackReason: s.fallback_reason ?? null,
      });
    } catch (e) {
      pushMessage({
        role: 'error',
        text: e instanceof Error ? e.message : 'Summary request failed.',
      });
    } finally {
      if (alive.current) setSummaryTyping(false);
    }
  };

  const dismissMessage = (id: number) => {
    setMessages((m) => m.filter((msg) => msg.id !== id));
    setOpenCitations((s) => {
      const next = new Set(s);
      next.delete(id);
      return next;
    });
  };

  const toggleCitations = (id: number) => {
    setOpenCitations((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <section className="card chat-card">
      <div className="chat-header">
        <h2>Gemini Analyst</h2>
        <span className="chat-badge">Server-side AI</span>
      </div>

      <div className="chat-summary">
        <div className="chat-summary-actions">
          <button
            className="btn btn-secondary"
            disabled={summaryTyping !== false}
            onClick={() => void summarize(true)}
          >
            {summaryTyping === 'gemini' ? 'Summarizing…' : 'Gemini Summary'}
          </button>
        </div>
        <p className="chat-summary-hint">Summarizes the latest trading window into the chat.</p>
      </div>

      <div className="chat-messages" ref={listRef}>
        {messages.length === 0 && !typing && !summaryTyping && (
          <p className="chat-empty">
            Ask about FIX messages or trading flow. AI is served by the backend.
          </p>
        )}
        {messages.map((m) =>
          m.summary ? (
            <div key={m.id} className="chat-bubble ai summary">
              <div className="summary-top">
                <span className="summary-label">Summary</span>
                <button
                  className="summary-close"
                  onClick={() => dismissMessage(m.id)}
                  title="Dismiss summary"
                  aria-label="Dismiss summary"
                >
                  ✕
                </button>
              </div>
              <div className="summary-body">{m.text}</div>
              <div className="chat-summary-meta">
                {m.provider && <span className="badge badge-ok">Provider: {m.provider}</span>}
                {m.fallbackReason && (
                  <span className="badge badge-warn">Fallback — {m.fallbackReason}</span>
                )}
              </div>
              {m.citations && m.citations.length > 0 && (
                <>
                  <button className="citations-toggle" onClick={() => toggleCitations(m.id)}>
                    {openCitations.has(m.id)
                      ? 'Hide citations'
                      : `Show citations (${m.citations.length})`}
                  </button>
                  {openCitations.has(m.id) && (
                    <ul className="citation-list">
                      {m.citations.map((c, i) => (
                        <li key={i} className="mono">
                          [{c}]
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              )}
            </div>
          ) : (
            <div key={m.id} className={`chat-bubble ${m.role}`}>
              {m.text}
            </div>
          ),
        )}
        {(typing || summaryTyping) && (
          <div className="chat-bubble ai typing" aria-label="typing">
            <span className="typing-dot" />
            <span className="typing-dot" />
            <span className="typing-dot" />
          </div>
        )}
      </div>

      <div className="chat-input-row">
        <textarea
          className="chat-input"
          rows={1}
          value={draft}
          placeholder="Type a message… (Enter to send, Shift+Enter for newline)"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
        />
        <button
          className="btn btn-primary chat-send"
          onClick={() => void send()}
          disabled={typing || !draft.trim()}
        >
          Send
        </button>
      </div>
    </section>
  );
}
