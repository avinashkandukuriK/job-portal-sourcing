import { Activity, Database, ExternalLink, Play, RefreshCw, Search, Server, Settings2, Users } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  AdapterResponse,
  PortalRunResponse,
  SearchResponse,
  SourcePlanResponse,
  apiBaseUrl,
  createSourcePlan,
  getAdapters,
  getHealth,
  runPortalSearch,
  runSearch,
} from "./api";

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
  const [planning, setPlanning] = useState(false);
  const [runningPortal, setRunningPortal] = useState<string | null>(null);
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [sourcePlan, setSourcePlan] = useState<SourcePlanResponse | null>(null);
  const [portalRun, setPortalRun] = useState<PortalRunResponse | null>(null);
  const [selectedState, setSelectedState] = useState("IL");
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

  async function handlePlanSources() {
    setPlanning(true);
    setError(null);
    setSourcePlan(null);
    setPortalRun(null);
    try {
      setSourcePlan(await createSourcePlan(jdText, selectedState));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Source planning failed");
    } finally {
      setPlanning(false);
    }
  }

  async function handleRunPortal(portalId: string) {
    setRunningPortal(portalId);
    setError(null);
    setPortalRun(null);
    try {
      setPortalRun(await runPortalSearch(jdText, selectedState, portalId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Portal run failed");
    } finally {
      setRunningPortal(null);
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
          <a className="nav-item" href="#workforce">
            <Users size={18} />
            Workforce
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

        <section className="panel workforce" id="workforce">
          <div className="panel-heading">
            <div>
              <p className="caption">Free workforce portals</p>
              <h2>Automated state portal sourcing</h2>
            </div>
            <div className="planner-actions">
              <label>
                State
                <select value={selectedState} onChange={(event) => setSelectedState(event.target.value)}>
                  <option value="CA">CA</option>
                  <option value="IL">IL</option>
                  <option value="FL">FL</option>
                  <option value="IN">IN</option>
                  <option value="MA">MA</option>
                </select>
              </label>
              <button className="primary-button" type="button" onClick={handlePlanSources} disabled={planning || !jdText.trim()}>
                <Search size={17} />
                {planning ? "Planning" : "Plan sources"}
              </button>
            </div>
          </div>

          {sourcePlan ? (
            <div className="portal-layout">
              <div className="parsed source-summary">
                <strong>{sourcePlan.parsed_jd.title}</strong>
                <span>{sourcePlan.state || "No state selected"}</span>
                <span>{sourcePlan.parsed_jd.required_skills.slice(0, 5).join(", ") || "No skills parsed"}</span>
              </div>
              {sourcePlan.message ? <div className="empty-state compact">{sourcePlan.message}</div> : null}
              {sourcePlan.recommended_portals.map((item) => (
                <article className="portal-row" key={item.portal.id}>
                  <div>
                    <strong>{item.portal.name}</strong>
                    <span>{item.portal.state_name} workforce portal</span>
                    <a href={item.portal.employer_url} target="_blank" rel="noreferrer">
                      Employer portal <ExternalLink size={14} />
                    </a>
                  </div>
                  <div className="tag-list">
                    {item.search_terms.slice(0, 8).map((term) => (
                      <span className="tag" key={term}>
                        {term}
                      </span>
                    ))}
                  </div>
                  <div className="readiness">
                    <span className={`status-pill ${item.automation_ready ? "ready" : "disabled_no_config"}`}>
                      {item.automation_ready ? "ready" : "needs setup"}
                    </span>
                    <small>{item.readiness_messages.join(" ")}</small>
                  </div>
                  <button
                    className="primary-button"
                    type="button"
                    onClick={() => handleRunPortal(item.portal.id)}
                    disabled={!item.automation_ready || runningPortal === item.portal.id}
                  >
                    <Play size={17} />
                    {!item.automation_ready
                      ? "Setup required"
                      : runningPortal === item.portal.id
                        ? "Running"
                        : "Run portal search"}
                  </button>
                </article>
              ))}
            </div>
          ) : (
            <div className="empty-state compact">Plan free sources to select a state workforce portal for this JD.</div>
          )}

          {portalRun ? (
            <div className="portal-results">
              <div className="panel-heading nested-heading">
                <div>
                  <p className="caption">Portal run</p>
                  <h2>
                    {portalRun.portal.name}: {statusLabel(portalRun.status)}
                  </h2>
                </div>
                <span className={`status-pill ${portalRun.status === "completed" ? "ready" : "disabled_no_config"}`}>
                  {portalRun.candidates_saved}/{portalRun.candidates_found} saved
                </span>
              </div>
              {portalRun.warnings.length ? <div className="warning-banner">{portalRun.warnings.join(" ")}</div> : null}
              {portalRun.error ? <div className="error-banner">{portalRun.error}</div> : null}
              {portalRun.candidates.length ? (
                <div className="candidate-grid">
                  {portalRun.candidates.map((item) => (
                    <article className="candidate-row portal-candidate" key={item.candidate.source_id}>
                      <div>
                        <strong>{item.candidate.name}</strong>
                        <span>{item.candidate.current_title || item.candidate.source}</span>
                        <span>{item.candidate.location || "Location unavailable"}</span>
                        <span>{item.candidate.contact.email || "No email"} | {item.candidate.contact.phone || "No phone"}</span>
                      </div>
                      <b>{item.saved ? "Saved" : "Hold"}</b>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="empty-state compact">No candidates returned. If this says needs setup, add portal credentials and enable the live connector.</div>
              )}
            </div>
          ) : null}
        </section>

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
