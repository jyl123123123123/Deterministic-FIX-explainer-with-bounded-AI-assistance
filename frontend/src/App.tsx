import { useState } from 'react';
import { parseFixMessage, type ParseResult } from './fix/parser';
import { buildExplanation, type Explanation } from './fix/explainer';
import { SAMPLES } from './fix/samples';
import Background from './Background';

type Tab = 'analyzer' | 'builder';

interface BuilderState {
  symbol: string;
  side: '1' | '2';
  quantity: string;
  orderType: '1' | '2';
  price: string;
}

type ExplanationMode = 'template' | 'ai';

interface ApiExplanation {
  provider_summary: string;
  fallback_used: boolean;
}

function formatUtcTimestamp(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return (
    `${d.getUTCFullYear()}${p(d.getUTCMonth() + 1)}${p(d.getUTCDate())}` +
    `-${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}`
  );
}

export default function App() {
  const [tab, setTab] = useState<Tab>('analyzer');
  const [input, setInput] = useState('');
  const [result, setResult] = useState<ParseResult | null>(null);
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [explanationMode, setExplanationMode] = useState<ExplanationMode>('template');
  const [apiExplanation, setApiExplanation] = useState<ApiExplanation | null>(null);
  const [apiLoading, setApiLoading] = useState(false);
  const [apiError, setApiError] = useState('');
  const [error, setError] = useState('');
  const [builder, setBuilder] = useState<BuilderState>({
    symbol: 'AAPL',
    side: '1',
    quantity: '100',
    orderType: '2',
    price: '185.50',
  });
  const [builderError, setBuilderError] = useState('');

  const analyze = async (message: string) => {
    if (!message.trim()) {
      setError('Please paste a FIX message first.');
      setResult(null);
      setExplanation(null);
      setApiExplanation(null);
      return;
    }
    try {
      const parsed = parseFixMessage(message);
      setResult(parsed);
      setExplanation(buildExplanation(parsed));
      setError('');
    } catch (e) {
      setResult(null);
      setExplanation(null);
      setError(e instanceof Error ? e.message : 'Failed to parse the message.');
      setApiExplanation(null);
      return;
    }

    setApiError('');
    setApiLoading(true);
    try {
      const response = await fetch('/api/explain', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, mode: explanationMode }),
      });
      if (!response.ok) {
        throw new Error(`Explanation API returned HTTP ${response.status}.`);
      }
      const data = (await response.json()) as { explanation?: ApiExplanation };
      if (!data.explanation?.provider_summary) {
        throw new Error('Explanation API returned no summary.');
      }
      setApiExplanation(data.explanation);
    } catch (e) {
      setApiExplanation(null);
      setApiError(e instanceof Error ? e.message : 'Explanation server is unavailable.');
    } finally {
      setApiLoading(false);
    }
  };

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
    let priceField = '';
    if (builder.orderType === '2') {
      const price = Number(builder.price);
      if (!Number.isFinite(price) || price <= 0) {
        setBuilderError('Limit price is required for limit orders.');
        return;
      }
      priceField = `44=${builder.price}|`;
    }
    setBuilderError('');
    const message =
      `8=FIX.4.2|35=D|49=FIXINSIGHT|56=EXCHANGE|34=1|52=${formatUtcTimestamp(new Date())}` +
      `|11=CLI-${Date.now()}|55=${symbol}|54=${builder.side}|38=${builder.quantity}` +
      `|40=${builder.orderType}|${priceField}59=0|10=000|`;
    setInput(message);
    setTab('analyzer');
    analyze(message);
  };

  const msgType = result?.byTag[35];
  const side = result?.byTag[54];
  const sideClass =
    side?.rawValue === '1' ? 'side-buy' : side?.rawValue === '2' ? 'side-sell' : '';

  return (
    <>
      <Background />
      <div className="app">
      <header className="header">
        <div>
          <h1>FIX Insight</h1>
          <p className="subtitle">Browser-only FIX protocol message analyzer</p>
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
        </nav>
      </header>

      {tab === 'analyzer' && (
        <main>
          <section className="card">
            <h2>Raw FIX Message</h2>
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
            <button className="btn btn-primary" onClick={() => analyze(input)}>
              Analyze Message
            </button>
            <label className="form-field explanation-mode">
              <span>Server explanation</span>
              <select
                value={explanationMode}
                onChange={(e) => setExplanationMode(e.target.value as ExplanationMode)}
              >
                <option value="template">Local template</option>
                <option value="ai">Gemini API</option>
              </select>
            </label>
            {apiLoading && <p className="hint">Requesting the explanation server...</p>}
            {apiError && <p className="error">{apiError}</p>}
            {error && <p className="error">{error}</p>}
            <p className="hint">
              Supports pipe (|), caret (^) and SOH (\u0001) delimiters — detected automatically.
            </p>
          </section>

          {result && (
            <>
              <section>
                <h2 className="section-title">Parsed Message</h2>
                <div className="card-grid">
                  <div className="card field-card">
                    <span className="field-label">Message Type</span>
                    <span className="field-value">{msgType ? msgType.decoded : '—'}</span>
                  </div>
                  <div className="card field-card">
                    <span className="field-label">Symbol</span>
                    <span className="field-value mono">{result.byTag[55]?.rawValue ?? '—'}</span>
                  </div>
                  <div className="card field-card">
                    <span className="field-label">Side</span>
                    <span className={`field-value ${sideClass}`}>{side ? side.decoded : '—'}</span>
                  </div>
                  <div className="card field-card">
                    <span className="field-label">Quantity</span>
                    <span className="field-value mono">{result.byTag[38]?.rawValue ?? '—'}</span>
                  </div>
                  <div className="card field-card">
                    <span className="field-label">Order Type</span>
                    <span className="field-value">{result.byTag[40]?.decoded ?? '—'}</span>
                  </div>
                  <div className="card field-card">
                    <span className="field-label">Limit Price</span>
                    <span className="field-value mono">
                      {result.byTag[44] ? `$${result.byTag[44].rawValue}` : '—'}
                    </span>
                  </div>
                </div>
              </section>

              <section>
                <h2 className="section-title">
                  Protocol Evidence{' '}
                  <span className="delimiter-note">delimiter: {result.delimiterName}</span>
                </h2>
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
                      {result.fields.map((f, i) => (
                        <tr key={`${f.tag}-${i}`} className={f.name.startsWith('Unknown') ? 'unknown-tag' : ''}>
                          <td className="mono tag-cell">{f.tag}</td>
                          <td>{f.name}</td>
                          <td className="mono">
                            {f.decoded !== f.rawValue ? (
                              <>
                                {f.decoded} <span className="raw-inline">({f.rawValue})</span>
                              </>
                            ) : (
                              f.rawValue
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              {explanation && (
                <section>
                  <h2 className="section-title">Explanation</h2>
                  <div className="card explanation-card">
                    <p className="explanation-text">{explanation.paragraph}</p>
                    <h3>Evidence</h3>
                    <ul className="evidence-list">
                      {explanation.evidence.map((e) => (
                        <li key={e} className="mono">
                          {e}
                        </li>
                      ))}
                    </ul>
                    <h3>Disclaimer</h3>
                    <ul className="disclaimer-list">
                      {explanation.disclaimers.map((d) => (
                        <li key={d}>{d}</li>
                      ))}
                    </ul>
                  </div>
                </section>
              )}
              {apiExplanation && (
                <section>
                  <h2 className="section-title">Server Explanation</h2>
                  <div className="card explanation-card">
                    <p className="explanation-text">{apiExplanation.provider_summary}</p>
                    <p className="hint">
                      {apiExplanation.fallback_used
                        ? 'The server used its deterministic fallback.'
                        : explanationMode === 'ai'
                          ? 'This summary was arranged by Gemini from approved facts.'
                          : 'This summary was rendered by the local template provider.'}
                    </p>
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
                  <option value="1">Market</option>
                </select>
              </label>
              <label className="form-field">
                <span>Limit Price</span>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={builder.price}
                  disabled={builder.orderType === '1'}
                  onChange={(e) => setBuilder({ ...builder, price: e.target.value })}
                />
              </label>
            </div>
            {builderError && <p className="error">{builderError}</p>}
            <button className="btn btn-primary" onClick={generateFix}>
              Generate FIX Message
            </button>
            <p className="hint">
              Generates a New Order Single (35=D) into the input box on the Analyzer tab and
              analyzes it immediately.
            </p>
          </section>
        </main>
      )}
      </div>
    </>
  );
}
