import { useEffect, useRef, useState } from 'react';
import { parseFixMessage, type ParseResult } from './fix/parser';
import { SAMPLES } from './fix/samples';
import { explainViaApi, ApiError, type ExplainResponse } from './api';
import { buildNewOrderSingle, toDisplay } from './fix/builder';
import Background from './Background';
import ChatPanel from './ChatPanel';
import TradingDashboard from './TradingDashboard';

type Tab = 'analyzer' | 'builder' | 'trading';
type Mode = 'backend' | 'local';

interface BuilderState {
  symbol: string;
  side: '1' | '2';
  quantity: string;
  orderType: '1' | '2';
  price: string;
}

/** Unified view model so backend and local results render identically. */
interface ViewField {
  tag: number;
  ordinal?: number;
  name: string;
  value: string;
  decoded: string;
  unknown: boolean;
}

interface ViewModel {
  msgType: string;
  symbol: string;
  sideText: string;
  sideRaw: string;
  quantity: string;
  orderType: string;
  price: string;
  fields: ViewField[];
}

function viewFromBackend(res: ExplainResponse): ViewModel {
  // Field names / enum labels come only from the deterministic known_facts
  // (keyed by ordinal so repeated tags resolve to the right occurrence).
  const factByOrdinal = new Map<number, NonNullable<ExplainResponse['deterministic']['known_facts'][number]['field']>>();
  for (const fact of res.deterministic.known_facts) {
    if (fact.field) factByOrdinal.set(fact.field.ordinal, fact.field);
  }
  const fields: ViewField[] = res.message.fields.map((entry) => {
    const fact = factByOrdinal.get(entry.ordinal);
    const name = fact?.field_name ?? `Tag ${entry.tag}`;
    return {
      tag: entry.tag,
      ordinal: entry.ordinal,
      name,
      value: entry.value,
      decoded: fact?.enum_name ?? entry.value,
      unknown: !fact?.field_name,
    };
  });
  const byTag = (t: number) => fields.find((f) => f.tag === t);
  const purpose = res.deterministic.known_facts.find((f) =>
    f.claim.startsWith('Message purpose is '),
  );
  return {
    msgType: purpose
      ? purpose.claim.slice('Message purpose is '.length).replace(/\.$/, '')
      : res.message.message_type,
    symbol: byTag(55)?.value ?? '—',
    sideText: byTag(54)?.decoded ?? '—',
    sideRaw: byTag(54)?.value ?? '',
    quantity: byTag(38)?.value ?? '—',
    orderType: byTag(40)?.decoded ?? '—',
    price: byTag(44) ? byTag(44)!.value : '—',
    fields,
  };
}

function viewFromLocal(parsed: ParseResult): ViewModel {
  const fields: ViewField[] = parsed.fields.map((f) => ({
    tag: f.tag,
    name: f.name,
    value: f.rawValue,
    decoded: f.decoded,
    unknown: f.name.startsWith('Unknown'),
  }));
  return {
    msgType: parsed.byTag[35]?.decoded ?? '—',
    symbol: parsed.byTag[55]?.rawValue ?? '—',
    sideText: parsed.byTag[54]?.decoded ?? '—',
    sideRaw: parsed.byTag[54]?.rawValue ?? '',
    quantity: parsed.byTag[38]?.rawValue ?? '—',
    orderType: parsed.byTag[40]?.decoded ?? '—',
    price: parsed.byTag[44] ? parsed.byTag[44].rawValue : '—',
    fields,
  };
}

export default function App() {
  const [tab, setTab] = useState<Tab>('analyzer');
  const [input, setInput] = useState('');
  const [mode, setMode] = useState<Mode | null>(null);
  const [view, setView] = useState<ViewModel | null>(null);
  const [backend, setBackend] = useState<ExplainResponse | null>(null);
  const [error, setError] = useState('');
  const [analyzing, setAnalyzing] = useState(false);
  const [builder, setBuilder] = useState<BuilderState>({
    symbol: 'AAPL',
    side: '1',
    quantity: '100',
    orderType: '2',
    price: '185.50',
  });
  const [builderError, setBuilderError] = useState('');
  const [generated, setGenerated] = useState('');
  const [copied, setCopied] = useState(false);
  const requestIdRef = useRef(0);
  const lastRequestedRef = useRef('');

  const clearResults = () => {
    setView(null);
    setBackend(null);
    setMode(null);
  };

  const analyze = async (message: string) => {
    if (!message.trim()) {
      setError('Please paste a FIX message first.');
      clearResults();
      return;
    }
    const requestId = ++requestIdRef.current;
    lastRequestedRef.current = message;
    setAnalyzing(true);
    try {
      const res = await explainViaApi(message);
      if (requestId !== requestIdRef.current) return; // stale response, input moved on
      setBackend(res);
      setView(viewFromBackend(res));
      setMode('backend');
      setError('');
    } catch (e) {
      if (requestId !== requestIdRef.current) return;
      if (e instanceof ApiError) {
        // The backend rejected the message itself; show its error verbatim.
        clearResults();
        setError(e.message);
      } else {
        // Backend unreachable / server failure: fall back to local parsing.
        try {
          const parsed = parseFixMessage(message);
          setView(viewFromLocal(parsed));
          setBackend(null);
          setMode('local');
          setError('');
        } catch (localErr) {
          clearResults();
          setError(localErr instanceof Error ? localErr.message : 'Failed to parse the message.');
        }
      }
    } finally {
      if (requestId === requestIdRef.current) setAnalyzing(false);
    }
  };

  // Auto-analyze with a debounce: 550ms after the user stops typing.
  // Empty input returns to the blank state; stale in-flight requests are
  // invalidated via requestIdRef so their responses are ignored.
  useEffect(() => {
    const msg = input;
    if (!msg.trim()) {
      requestIdRef.current++;
      lastRequestedRef.current = '';
      setAnalyzing(false);
      clearResults();
      setError('');
      return;
    }
    if (msg === lastRequestedRef.current) return; // already requested (button / builder)
    requestIdRef.current++; // invalidate any in-flight request for older input
    const timer = setTimeout(() => {
      if (msg !== lastRequestedRef.current) void analyze(msg);
    }, 550);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [input]);

  // Lock vertical scroll on the blank initial page (desktop only); unlock as
  // soon as results or an error make the page taller than one viewport.
  // The Trading Flow tab always needs scrolling, so never lock there.
  const hasResults = Boolean(view || error);
  useEffect(() => {
    document.body.classList.toggle('no-scroll', !hasResults && tab !== 'trading');
    return () => document.body.classList.remove('no-scroll');
  }, [hasResults, tab]);

  const fillSample = (message: string) => {
    setInput(message);
    setError('');
  };

  const generateFix = () => {
    const symbol = builder.symbol.trim().toUpperCase();
    const qty = Number(builder.quantity);
    if (!symbol) {
      setBuilderError('Symbol is required.');
      return;
    }
    if (!Number.isFinite(qty) || qty <= 0) {
      setBuilderError('Quantity must be a positive number.');
      return;
    }
    let price: string | undefined;
    if (builder.orderType === '2') {
      const p = Number(builder.price);
      if (!Number.isFinite(p) || p <= 0) {
        setBuilderError('Limit price is required for limit orders.');
        return;
      }
      price = builder.price;
    }
    setBuilderError('');
    const message = toDisplay(
      buildNewOrderSingle({
        symbol,
        side: builder.side,
        quantity: builder.quantity,
        orderType: builder.orderType,
        price,
      }),
    );
    // Stay on this tab: show the generated message inline; analysis is opt-in.
    setGenerated(message);
    setCopied(false);
  };

  const copyGenerated = async () => {
    try {
      await navigator.clipboard.writeText(generated);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard API unavailable (e.g. permissions); user can copy manually.
    }
  };

  const analyzeGenerated = () => {
    setInput(generated);
    setTab('analyzer');
    void analyze(generated);
  };

  const sideClass = view?.sideRaw === '1' ? 'side-buy' : view?.sideRaw === '2' ? 'side-sell' : '';
  const providerLabel = backend?.provider === 'gemini' ? 'Gemini' : 'Template';

  return (
    <>
      <Background />
      <div className="app">
      <header className="header">
        <div>
          <h1>FIX Insight</h1>
          <p className="subtitle">FIX protocol message analyzer</p>
        </div>
        <nav className="tabs">
          <button
            className={tab === 'analyzer' ? 'tab active' : 'tab'}
            onClick={() => setTab('analyzer')}
          >
            Message Analyzer
          </button>
          <button
            className={tab === 'builder' ? 'tab active' : 'tab'}
            onClick={() => setTab('builder')}
          >
            Order Builder
          </button>
          <button className={tab === 'trading' ? 'tab active' : 'tab'} onClick={() => setTab('trading')}>Trading Flow</button>
        </nav>
      </header>

      <div className="content-row">
        <div className="main-col">
      {tab === 'trading' && <TradingDashboard />}
      {tab === 'analyzer' && (
        <main>
          <section className="card">
            <h2>
              Raw FIX Message
              {analyzing && <span className="analyzing-hint">Analyzing…</span>}
            </h2>
            <textarea
              className="raw-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="35=D|55=AAPL|54=1|38=100|40=2|44=185.50"
              rows={4}
              spellCheck={false}
            />
            <div className="sample-row">
              {SAMPLES.map((s) => (
                <button key={s.label} className="btn btn-secondary" onClick={() => fillSample(s.message)}>
                  {s.label}
                </button>
              ))}
            </div>
            <button className="btn btn-primary" onClick={() => void analyze(input)} disabled={analyzing}>
              {analyzing ? 'Analyzing…' : 'Analyze Message'}
            </button>
            {error && <p className="error">{error}</p>}
            <p className="hint">
              Supports pipe (|), caret (^) and SOH () delimiters — detected automatically.
            </p>
          </section>

          {view && (
            <div className="status-row">
              {mode === 'backend' && backend && !backend.fallback_used && (
                <span className="badge badge-ok">Provider: {providerLabel}</span>
              )}
              {mode === 'backend' && backend?.fallback_used && (
                <span className="badge badge-warn">
                  Fallback result (Provider: {providerLabel}) — reason:{' '}
                  {backend.fallback_reason ?? 'unknown'}
                </span>
              )}
              {mode === 'local' && (
                <span className="badge badge-warn">Local mode (backend offline)</span>
              )}
            </div>
          )}

          {view && (
            <>
              <section>
                <h2 className="section-title">Parsed Message</h2>
                <div className="card-grid">
                  <div className="card field-card">
                    <span className="field-label">Message Type</span>
                    <span className="field-value">{view.msgType}</span>
                  </div>
                  <div className="card field-card">
                    <span className="field-label">Symbol</span>
                    <span className="field-value mono">{view.symbol}</span>
                  </div>
                  <div className="card field-card">
                    <span className="field-label">Side</span>
                    <span className={`field-value ${sideClass}`}>{view.sideText}</span>
                  </div>
                  <div className="card field-card">
                    <span className="field-label">Quantity</span>
                    <span className="field-value mono">{view.quantity}</span>
                  </div>
                  <div className="card field-card">
                    <span className="field-label">Order Type</span>
                    <span className="field-value">{view.orderType}</span>
                  </div>
                  <div className="card field-card">
                    <span className="field-label">Limit Price</span>
                    <span className="field-value mono">{view.price}</span>
                  </div>
                </div>
              </section>

              <section>
                <h2 className="section-title">Protocol Evidence</h2>
                <div className="card table-card">
                  <table className="evidence-table">
                    <thead>
                      <tr>
                        <th>Tag</th>
                        <th>Field</th>
                        <th>Decoded value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {view.fields.map((f, i) => (
                        <tr key={`${f.tag}-${f.ordinal ?? i}`} className={f.unknown ? 'unknown-tag' : ''}>
                          <td className="mono tag-cell">{f.tag}</td>
                          <td>{f.name}</td>
                          <td className="mono">
                            {f.decoded !== f.value ? (
                              <>
                                {f.decoded} <span className="raw-inline">({f.value})</span>
                              </>
                            ) : (
                              f.value
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              {mode === 'backend' && backend && (
                <section>
                    <h2 className="section-title">
                      Findings{' '}
                      <span className="delimiter-note">
                        {backend.deterministic.validation_errors.length} validation record(s)
                      </span>
                    </h2>
                    <div className="card table-card">
                      {backend.deterministic.validation_errors.length === 0 ? (
                        <p className="findings-empty">No validation findings.</p>
                      ) : (
                        <table className="evidence-table">
                          <thead>
                            <tr>
                              <th>Severity</th>
                              <th>Code</th>
                              <th>Tag / Ordinal</th>
                              <th>Message</th>
                            </tr>
                          </thead>
                          <tbody>
                            {backend.deterministic.validation_errors.map((f, i) => (
                              <tr key={`${f.code}-${i}`}>
                                <td>
                                  <span className={`severity severity-${f.severity}`}>{f.severity}</span>
                                </td>
                                <td className="mono">{f.code}</td>
                                <td className="mono">
                                  {f.tag ?? '—'} / {f.ordinal ?? '—'}
                                </td>
                                <td>{f.message}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </div>
                  </section>
              )}
            </>
          )}
        </main>
      )}

      {tab === 'builder' && (
        <main>
          <section className="card builder-card">
            <h2>Order Builder</h2>
            <div className="form-grid">
              <label className="form-field">
                <span>Symbol</span>
                <input
                  value={builder.symbol}
                  onChange={(e) => setBuilder({ ...builder, symbol: e.target.value })}
                  placeholder="AAPL"
                />
              </label>
              <div className="form-field">
                <span>Side</span>
                <div className="side-toggle">
                  <button
                    className={builder.side === '1' ? 'toggle-btn buy active' : 'toggle-btn buy'}
                    onClick={() => setBuilder({ ...builder, side: '1' })}
                  >
                    Buy
                  </button>
                  <button
                    className={builder.side === '2' ? 'toggle-btn sell active' : 'toggle-btn sell'}
                    onClick={() => setBuilder({ ...builder, side: '2' })}
                  >
                    Sell
                  </button>
                </div>
              </div>
              <label className="form-field">
                <span>Quantity</span>
                <input
                  type="number"
                  min="1"
                  value={builder.quantity}
                  onChange={(e) => setBuilder({ ...builder, quantity: e.target.value })}
                />
              </label>
              <label className="form-field">
                <span>Order Type</span>
                <select
                  value={builder.orderType}
                  onChange={(e) =>
                    setBuilder({ ...builder, orderType: e.target.value as '1' | '2' })
                  }
                >
                  <option value="2">Limit</option>
                </select>
              </label>
              <label className="form-field">
                <span>Limit Price</span>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={builder.price}
                  onChange={(e) => setBuilder({ ...builder, price: e.target.value })}
                />
              </label>
            </div>
            {builderError && <p className="error">{builderError}</p>}
            <button className="btn btn-primary" onClick={generateFix}>
              Generate FIX Message
            </button>
            <p className="hint">
              Generates a complete New Order Single (35=D) with valid BodyLength and CheckSum,
              shown below. Pipe (|) is a readable rendering; the analyzer converts it to SOH.
              Only Limit is offered: the loaded Orchestra subset defines OrdType=2 (Limit) as
              the sole valid value.
            </p>
            {generated && (
              <div className="builder-result">
                <h3>Generated FIX Message</h3>
                <pre className="generated-message">{generated}</pre>
                <div className="builder-result-actions">
                  <button className="btn btn-secondary" onClick={() => void copyGenerated()}>
                    {copied ? 'Copied!' : 'Copy'}
                  </button>
                  <button className="btn btn-primary" onClick={analyzeGenerated}>
                    Analyze this message
                  </button>
                </div>
              </div>
            )}
          </section>
        </main>
      )}
        </div>
        <aside className="chat-col">
          <ChatPanel />
        </aside>
      </div>
      </div>
    </>
  );
}
