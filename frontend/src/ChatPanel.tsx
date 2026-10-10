/** Model calls go through the bounded backend; no browser-stored credentials. */
export default function ChatPanel() {
 return <aside className="card"><h3>Bounded AI</h3><p>Open Trading Flow to request a cited aggregate summary from the Python backend.</p><p>Keys stay server-side. Statistics and template summaries work without a key.</p><p>General chat is disabled so responses cannot invent protocol or trading facts.</p></aside>;
}
