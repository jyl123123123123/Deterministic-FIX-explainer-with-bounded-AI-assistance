import {useEffect, useState} from 'react';
type Row = {symbol: string; currency: string; buy_order_qty: number; sell_order_qty: number; buy_fill_qty: number; sell_fill_qty: number; buy_notional: string; sell_notional: string; gross_notional: string};
type Report = {snapshot_id: string; window_start: string; window_end: string; total_orders: number; total_executions: number; symbols: Row[]; currency_totals: {currency: string; gross_notional: string}[]; findings: Record<string, number>; anomalies: {symbol: string; side: string; previous: number; current: number}[]};
type Run = {run_id: string; status: string; processed: number; total_messages: number; rate: number};
type Summary = {summary: string; provider: string; fallback_reason: string | null; report: Report};
async function request<T>(path: string, method = 'GET'): Promise<T> {
 const response = await fetch(path, {method}); const data = await response.json();
 if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `HTTP ${response.status}`);
 return data as T;
}
function compareDecimal(a: string, b: string) {
 const [aw, af = ''] = a.split('.'), [bw, bf = ''] = b.split('.');
 if (aw.length !== bw.length) return bw.length - aw.length;
 return bw.localeCompare(aw) || bf.padEnd(12, '0').localeCompare(af.padEnd(12, '0'));
}
export default function TradingDashboard() {
 const [report, setReport] = useState<Report | null>(null), [run, setRun] = useState<Run | null>(null);
 const [trend, setTrend] = useState<number[]>([]);
 const [rate, setRate] = useState(25), [error, setError] = useState(''), [busy, setBusy] = useState(false);
 const [summary, setSummary] = useState<Summary | null>(null);
 const [sort, setSort] = useState<'buy_notional' | 'sell_notional' | 'gross_notional'>('gross_notional');
 useEffect(() => {
  let alive = true; let timer: ReturnType<typeof setTimeout>;
  const poll = async () => {
   try {
    const data = await request<Report>('/api/analytics/snapshot');
    const current = await request<Run | null>('/api/trading/active');
    if (alive) {setReport(data); setRun(current); setTrend(points => [...points.slice(-59), data.total_executions]);}
   } catch {if (alive) setError('Trading backend unavailable. Start the current Python FastAPI server.');}
   if (alive) timer = setTimeout(poll, 1000);
  };
  void poll(); return () => {alive = false; clearTimeout(timer);};
 }, []);
 const act = async (action: string) => {
  setBusy(true); setError('');
  try {
   if (action === 'start') {setRun(await request<Run>(`/api/trading/start?count=1500&rate=${rate}`, 'POST')); setSummary(null); setTrend([]);}
   else if (run) setRun(await request<Run>(`/api/trading/runs/${run.run_id}/${action}?rate=${rate}`, 'POST'));
  } catch(e) {setError(e instanceof Error ? e.message : 'Request failed');} finally {setBusy(false);}
 };
 const summarize = async (ai: boolean) => {
  setBusy(true); setError('');
  try {setSummary(await request<Summary>(`/api/analytics/summary?ai=${ai}`, 'POST'));}
  catch(e) {setError(e instanceof Error ? e.message : 'Summary failed');} finally {setBusy(false);}
 };
 const active = run && ['RUNNING', 'PAUSED'].includes(run.status);
 const rows = [...(report?.symbols ?? [])].sort((a,b) => a.currency.localeCompare(b.currency) || compareDecimal(a[sort],b[sort]) || a.symbol.localeCompare(b.symbol));
 return <main className="trading-dashboard"><h2>Live Trading Flow · Simulated Data</h2>
 <p>Connected FIX sessions only. Reported sides are not aggressor direction or market-wide demand.</p>
 <div className="card"><label>Replay speed <select value={rate} onChange={e => setRate(Number(e.target.value))}>{[10,25,50,100].map(n => <option key={n} value={n}>{n} messages/second</option>)}</select></label>{' '}
 <button disabled={busy || !!active} onClick={() => void act('start')}>Start new replay</button>{' '}
 <button disabled={busy || !active} onClick={() => void act(run?.status === 'PAUSED' ? 'resume' : 'pause')}>{run?.status === 'PAUSED' ? 'Resume / apply speed' : 'Pause / apply speed'}</button>{' '}
 <button disabled={busy || !active} onClick={() => void act('stop')}>Stop</button>
 <p>{run ? `${run.status}: ${run.processed}/${run.total_messages} messages · ${run.rate}/second` : 'No replay started in this browser.'}</p>
 <p>A new replay resets order state and statistics; the AI call budget is retained.</p></div>
 {error && <p role="alert">{error}</p>}
 {report && <><div className="card"><strong>{report.total_executions} fills · {report.total_orders} order requests</strong>
 <p>5-minute event-time window: {report.window_start} to {report.window_end}</p>
 {report.currency_totals.map(c => <p key={c.currency}>Gross traded value ({c.currency}): {c.gross_notional}</p>)}
 <p>UNSPECIFIED has no implied USD denomination. No FX conversion or contract multiplier.</p></div>
 <h3>Recent reported-fill count (live polling)</h3>
 <svg viewBox="0 0 600 120" role="img" aria-label="Reported-fill count over the last sixty polls" style={{width:'100%',maxHeight:160}}>
 <polyline fill="none" stroke="#34d399" strokeWidth="3" points={trend.map((n,i) => `${i * 600 / Math.max(1,trend.length-1)},${110 - n * 100 / Math.max(1,...trend)}`).join(' ')} />
 </svg><p>This trend shows rolling-window fill counts, not price or market performance.</p>
 <h3>Instrument rankings (within each currency)</h3><select aria-label="Rank instruments" value={sort} onChange={e => setSort(e.target.value as typeof sort)}><option value="gross_notional">Gross value</option><option value="buy_notional">Top bought</option><option value="sell_notional">Top sold</option></select>
 <div className="card table-card"><table className="evidence-table"><thead><tr>{['Symbol','Currency','Buy demand qty','Sell demand qty','Buy fill qty','Sell fill qty','Buy value','Sell value'].map(h => <th key={h}>{h}</th>)}</tr></thead><tbody>{rows.map(r => <tr key={`${r.symbol}-${r.currency}`}><td>{r.symbol}</td><td>{r.currency}</td><td>{r.buy_order_qty}</td><td>{r.sell_order_qty}</td><td>{r.buy_fill_qty}</td><td>{r.sell_fill_qty}</td><td>{r.buy_notional}</td><td>{r.sell_notional}</td></tr>)}</tbody></table></div>
 <h3>Window comparisons</h3>{report.anomalies.length ? report.anomalies.map((a,i) => <p key={i}>{a.symbol} {a.side}: {a.previous} → {a.current} reported fill quantity.</p>) : <p>No threshold crossings.</p>}
 <p>Excluded-event findings: {JSON.stringify(report.findings)}</p>
 <h3>Bounded flow summary</h3><button disabled={busy} onClick={() => void summarize(false)}>Template summary (no API)</button>{' '}<button disabled={busy} onClick={() => void summarize(true)}>Gemini summary (may incur costs)</button><p>No background AI requests. Requires server-side opt-in.</p></>}
 {summary && <div className="card"><p>Provider: {summary.provider} {summary.fallback_reason ?? ''}</p><p>Summary snapshot ends at {summary.report.window_end}; live statistics may have advanced.</p><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{summary.summary}</pre><details><summary>Referenced snapshot evidence</summary><pre style={{whiteSpace:'pre-wrap'}}>{JSON.stringify(summary.report,null,2)}</pre></details></div>}
 </main>;
}
