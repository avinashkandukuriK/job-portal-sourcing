import { Activity, Database, Play, RefreshCw, Search, Server, Settings2 } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { AdapterResponse, SearchResponse, apiBaseUrl, getAdapters, getHealth, runSearch } from "./api";

const sampleJd = `Forklift Operator needed in Albuquerque, NM.
Pay Rate: $20/hr. Shift: 6:30 am - 2:30 pm.
Must have forklift, warehouse, loading, unloading, and safety experience.
Background check and 4 panel drug test required.`;

function statusLabel(status: string) {
  return status.replaceAll("_", " ");
}

export function App() {
  const [jdText, setJdText] = useState(sampleJd);
  const [health, setHealth] = useState<"checking" | "ok" | "error">("checking");
  const [adapters, setAdapters] = useState<AdapterResponse[]>([]);
  const [loadingAdapters, setLoadingAdapters] = useState(true);
  const [searching, setSearching] = useState(false);
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const readyCount = useMemo(() => adapters.filter((adapter) => adapter.status === "ready").length, [adapters]);

  async function refreshRuntime() {
    setError(null);
    setLoadingAdapters(true);
    try {
      const [healthResponse, adapterResponse] = await Promise.all([getHealth(), getAdapters()]);
      setHealth(healthResponse.status === "ok" ? "ok" : "error");
      setAdapters(adapterResponse);
    } catch (err) {
      setHealth("error");
      setError(err instanceof Error ? err.message : "Could not reach backend");
    } finally {
      setLoadingAdapters(false);
    }
  }

  useEffect(() => {
    void refreshRuntime();
  }, []);

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSearching(true);
    setError(null);
    setResult(null);
    try {
      setResult(await runSearch(jdText));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setSearching(false);
    }
  }

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="Workspace navigation">
        <div className="brand">
          <div className="brand-mark">S</div>
          <div>
            <strong>Sourcing</strong>
            <span>Candidate portal</span>
          </div>
        </div>
        <nav className="nav-list">
          <a className="nav-item active" href="#search">
            <Search size={18} />
            Search
          </a>
          <a className="nav-item" href="#adapters">
            <Settings2 size={18} />
            Sources
          </a>
          <a className="nav-item" href="#runtime">
            <Server size={18} />
            Runtime
          </a>
        </nav>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="caption">Backend API</p>
            <h1>Candidate sourcing console</h1>
          </div>
          <button className="icon-button" type="button" onClick={refreshRuntime} aria-label="Refresh backend status">
            <RefreshCw size={18} />
          </button>
        </header>

        <section className="status-strip" id="runtime">
          <div className="status-card">
            <Activity size={20} />
            <div>
              <span>API status</span>
              <strong className={health === "ok" ? "good" : health === "checking" ? "muted" : "bad"}>
                {health === "checking" ? "Checking" : health === "ok" ? "Online" : "Needs attention"}
              </strong>
            </div>
          </div>
          <div className="status-card wide">
            <Server size={20} />
            <div>
              <span>Base URL</span>
              <strong>{apiBaseUrl}</strong>
            </div>
          </div>
          <div className="status-card">
            <Database size={20} />
            <div>
              <span>Ready sources</span>
              <strong>{loadingAdapters ? "Loading" : `${readyCount}/${adapters.length}`}</strong>
            </div>
          </div>
        </section>

        {error ? <div className="error-banner">{error}</div> : null}

        <div className="content-grid">
          <form className="panel composer" id="search" onSubmit={handleSearch}>
            <div className="panel-heading">
              <div>
                <p className="caption">Job description</p>
                <h2>Run a sourcing pass</h2>
              </div>
              <button className="primary-button" type="submit" disabled={searching || !jdText.trim()}>
                <Play size={17} />
                {searching ? "Searching" : "Search"}
              </button>
            </div>
            <textarea
              value={jdText}
              onChange={(event) => setJdText(event.target.value)}
              aria-label="Job description"
              spellCheck="true"
            />
          </form>

          <section className="panel results" aria-live="polite">
            <div className="panel-heading">
              <div>
                <p className="caption">Response</p>
                <h2>Ranked candidates</h2>
              </div>
            </div>
            {result ? (
              <div className="result-stack">
                <div className="parsed">
                  <strong>{result.parsed_jd.title}</strong>
                  <span>{result.parsed_jd.location || "Location not parsed"}</span>
                  <span>{result.parsed_jd.required_skills.slice(0, 4).join(", ") || "No skills parsed"}</span>
                </div>
                {result.candidates.length ? (
                  result.candidates.slice(0, 6).map((item) => (
                    <article className="candidate-row" key={`${item.candidate.source}-${item.candidate.name}`}>
                      <div>
                        <strong>{item.candidate.name}</strong>
                        <span>{item.candidate.current_title || item.candidate.source}</span>
                      </div>
                      <b>{item.score}</b>
                    </article>
                  ))
                ) : (
                  <div className="empty-state">No candidates returned yet. Add Supabase and source credentials for deeper results.</div>
                )}
              </div>
            ) : (
              <div className="empty-state">Search results will appear here after the backend responds.</div>
            )}
          </section>
        </div>

        <section className="panel adapters" id="adapters">
          <div className="panel-heading">
            <div>
              <p className="caption">Sources</p>
              <h2>Adapter readiness</h2>
            </div>
          </div>
          <div className="adapter-table">
            {adapters.map((adapter) => (
              <div className="adapter-row" key={adapter.metadata.name}>
                <div>
                  <strong>{adapter.metadata.display_name}</strong>
                  <span>{adapter.metadata.tier}</span>
                </div>
                <span className={`status-pill ${adapter.status}`}>{statusLabel(adapter.status)}</span>
                <span>{adapter.disabled_reason || "Ready to run"}</span>
              </div>
            ))}
          </div>
        </section>
      </section>
    </main>
  );
}
