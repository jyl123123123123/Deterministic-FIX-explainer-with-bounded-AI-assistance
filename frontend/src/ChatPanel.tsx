import { useEffect, useRef, useState } from 'react';

interface ChatMessage {
  id: number;
  role: 'user' | 'ai' | 'error';
  text: string;
}

const KEY_STORAGE = 'gemini_api_key';
const MODEL_STORAGE = 'gemini_model';
const DEFAULT_MODEL = 'gemini-2.0-flash';
const API_HOST = 'https://generativelanguage.googleapis.com';

const SYSTEM_INSTRUCTION =
  'You are a helpful assistant embedded in FIX Insight, a FIX protocol message analyzer. Answer concisely.';

interface GeminiPart {
  text?: string;
}

interface GeminiResponse {
  candidates?: Array<{ content?: { parts?: GeminiPart[] } }>;
}

async function callGemini(
  apiKey: string,
  model: string,
  history: ChatMessage[],
): Promise<string> {
  // Conversation history for the API: user/model roles only, and consecutive
  // same-role messages are merged (Gemini multi-turn expects alternation).
  const contents: Array<{ role: 'user' | 'model'; parts: [{ text: string }] }> = [];
  for (const m of history) {
    if (m.role === 'error') continue;
    const role = m.role === 'user' ? ('user' as const) : ('model' as const);
    const last = contents[contents.length - 1];
    if (last && last.role === role) {
      last.parts[0].text += `\n${m.text}`;
    } else {
      contents.push({ role, parts: [{ text: m.text }] });
    }
  }

  let resp: Response;
  try {
    resp = await fetch(
      `${API_HOST}/v1beta/models/${encodeURIComponent(model)}:generateContent`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-goog-api-key': apiKey,
        },
        body: JSON.stringify({
          systemInstruction: { parts: [{ text: SYSTEM_INSTRUCTION }] },
          contents,
        }),
      },
    );
  } catch {
    throw new Error('Network error: could not reach the Gemini API.');
  }

  if (!resp.ok) {
    if (resp.status === 401 || resp.status === 403) {
      throw new Error('Invalid API key (HTTP 401/403). Check your key and try again.');
    }
    if (resp.status === 404) {
      throw new Error(`Model not found (HTTP 404). Check the model name "${model}".`);
    }
    if (resp.status === 429) {
      throw new Error('Quota exceeded (HTTP 429). Check your Gemini plan and rate limits.');
    }
    throw new Error(`Gemini request failed (HTTP ${resp.status}).`);
  }

  const data = (await resp.json()) as GeminiResponse;
  const text = (data.candidates?.[0]?.content?.parts ?? [])
    .map((p) => p.text ?? '')
    .join('')
    .trim();
  return text || '(empty response from Gemini)';
}

export default function ChatPanel() {
  const [apiKey, setApiKey] = useState(() => localStorage.getItem(KEY_STORAGE) ?? '');
  const [model, setModel] = useState(
    () => localStorage.getItem(MODEL_STORAGE) ?? DEFAULT_MODEL,
  );
  const [keyDraft, setKeyDraft] = useState(apiKey);
  const [modelDraft, setModelDraft] = useState(model);
  const [showKey, setShowKey] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(!apiKey);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [typing, setTyping] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const nextId = useRef(1);
  const alive = useRef(true);

  // Keep the message list pinned to the bottom as content arrives.
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, typing]);

  useEffect(
    () => () => {
      alive.current = false;
    },
    [],
  );

  const saveSettings = () => {
    const key = keyDraft.trim();
    const mdl = modelDraft.trim() || DEFAULT_MODEL;
    if (!key) return;
    localStorage.setItem(KEY_STORAGE, key);
    localStorage.setItem(MODEL_STORAGE, mdl);
    setApiKey(key);
    setModel(mdl);
    setSettingsOpen(false);
  };

  const clearSettings = () => {
    localStorage.removeItem(KEY_STORAGE);
    localStorage.removeItem(MODEL_STORAGE);
    setApiKey('');
    setModel(DEFAULT_MODEL);
    setKeyDraft('');
    setModelDraft(DEFAULT_MODEL);
    setSettingsOpen(true);
  };

  const openSettings = () => {
    setKeyDraft(apiKey);
    setModelDraft(model);
    setSettingsOpen(true);
  };

  const send = async () => {
    const text = draft.trim();
    if (!text || !apiKey || typing) return;
    const userMsg: ChatMessage = { id: nextId.current++, role: 'user', text };
    const history = [...messages, userMsg];
    setMessages(history);
    setDraft('');
    setTyping(true);
    try {
      const reply = await callGemini(apiKey, model, history);
      if (!alive.current) return;
      setMessages((m) => [...m, { id: nextId.current++, role: 'ai', text: reply }]);
    } catch (e) {
      if (!alive.current) return;
      setMessages((m) => [
        ...m,
        {
          id: nextId.current++,
          role: 'error',
          text: e instanceof Error ? e.message : 'Gemini request failed.',
        },
      ]);
    } finally {
      if (alive.current) setTyping(false);
    }
  };

  return (
    <section className="card chat-card">
      <div className="chat-header">
        <h2>Gemini Chat</h2>
        {apiKey ? (
          <span className="chat-badge chat-badge-connected">Connected (your key)</span>
        ) : (
          <span className="chat-badge">UI preview — not connected</span>
        )}
      </div>

      {settingsOpen ? (
        <div className="chat-settings">
          <div className="chat-settings-row">
            <input
              type={showKey ? 'text' : 'password'}
              className="chat-settings-input mono"
              value={keyDraft}
              onChange={(e) => setKeyDraft(e.target.value)}
              placeholder="Gemini API key"
              autoComplete="off"
              spellCheck={false}
            />
            <button
              className="btn btn-secondary icon-btn"
              onClick={() => setShowKey((s) => !s)}
              title={showKey ? 'Hide key' : 'Show key'}
            >
              {showKey ? 'Hide' : 'Show'}
            </button>
          </div>
          <div className="chat-settings-row">
            <input
              className="chat-settings-input mono"
              value={modelDraft}
              onChange={(e) => setModelDraft(e.target.value)}
              placeholder={DEFAULT_MODEL}
              spellCheck={false}
            />
            <button
              className="btn btn-primary chat-settings-save"
              onClick={saveSettings}
              disabled={!keyDraft.trim()}
            >
              Save
            </button>
          </div>
          <p className="chat-settings-note">
            Key is stored only in this browser's localStorage and sent only to
            generativelanguage.googleapis.com.
          </p>
        </div>
      ) : (
        <div className="chat-status-row">
          <span className="chat-status-text mono">Key saved · model: {model}</span>
          <button className="btn btn-secondary icon-btn" onClick={openSettings}>
            Edit
          </button>
          <button className="btn btn-secondary icon-btn" onClick={clearSettings}>
            Clear
          </button>
        </div>
      )}

      <div className="chat-messages" ref={listRef}>
        {messages.length === 0 && !typing && (
          <p className="chat-empty">
            {apiKey
              ? 'Ask a question about a FIX message…'
              : 'Save your API key above, then ask a question about a FIX message…'}
          </p>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`chat-bubble ${m.role}`}>
            {m.text}
          </div>
        ))}
        {typing && (
          <div className="chat-bubble ai typing" aria-label="typing">
            <span className="typing-dot" />
            <span className="typing-dot" />
            <span className="typing-dot" />
          </div>
        )}
      </div>

      {!apiKey && (
        <p className="chat-hint">
          Enter your Gemini API key above to start chatting.{' '}
          <a href="https://aistudio.google.com/api-keys" target="_blank" rel="noreferrer">
            Get a key
          </a>
        </p>
      )}

      <div className="chat-input-row">
        <textarea
          className="chat-input"
          rows={1}
          value={draft}
          disabled={!apiKey}
          placeholder={
            apiKey
              ? 'Type a message… (Enter to send, Shift+Enter for newline)'
              : 'Enter your Gemini API key above to start chatting'
          }
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
          disabled={!apiKey || typing || !draft.trim()}
        >
          Send
        </button>
      </div>
    </section>
  );
}
