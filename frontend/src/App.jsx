import { useState, useEffect, useCallback } from "react";
import { listDocuments, deleteDocument, getStats, getHealth } from "./api.js";

import UploadPanel    from "./components/UploadPanel.jsx";
import DocumentList   from "./components/DocumentList.jsx";
import SearchPanel    from "./components/SearchPanel.jsx";
import DocumentViewer from "./components/DocumentViewer.jsx";
import ChatBox        from "./components/ChatBox.jsx";
import StatsBar       from "./components/StatsBar.jsx";
import GraphPage      from "./components/GraphPage.jsx";
import OfflineLoader  from "./components/OfflineLoader.jsx";
import "./components/OfflineLoader.css";
import "./App.css";
import "./components/GraphPage.css";

const HEALTH_POLL_MS     = 30_000;
const RETRY_INTERVAL_MS  = 5_000;

export default function App() {
  const [docs,                  setDocs]                = useState([]);
  const [stats,                 setStats]               = useState(null);
  const [health,                setHealth]              = useState(null);
  const [selectedDoc,           setSelectedDoc]         = useState(null);
  const [activeCitationChunkId, setActiveCitation]      = useState(null);
  const [sidebarTab,            setSidebarTab]          = useState("docs");
  const [page,                  setPage]                = useState("main");
  const [backendStatus,         setBackendStatus]       = useState("connecting");

const checkHealth = useCallback(async () => {
  try {
    const h = await getHealth();
    if (h?.status === "ok") {
      setHealth(h);
      setBackendStatus("ready");
      return true;
    }


    return false;

  } catch (e) {

    return false;
  }
}, []);

  const reload = useCallback(async () => {
    try { setDocs(await listDocuments()); } catch {}
    try { setStats(await getStats()); }    catch {}
  }, []);

  // On mount: check health, then load data if healthy.
  useEffect(() => {
    checkHealth().then((ok) => { if (ok) reload(); });
  }, [checkHealth, reload]);

  // While offline: retry health every 5 s automatically.
  useEffect(() => {
    if (backendStatus === "ready") return;
    const id = setInterval(() => {
      checkHealth().then((ok) => { if (ok) reload(); });
    }, RETRY_INTERVAL_MS);
    return () => clearInterval(id);
  }, [backendStatus, checkHealth, reload]);

  // Once online: keep health fresh every 30 s.
  useEffect(() => {
    if (backendStatus !== "ready") return;
    const id = setInterval(checkHealth, HEALTH_POLL_MS);
    return () => clearInterval(id);
  }, [backendStatus, checkHealth]);

  const handleUploaded = (doc) => {
    reload();
    setSelectedDoc(doc);
  };

  const handleDelete = async (docId) => {
    try { await deleteDocument(docId); } catch {}
    if (selectedDoc?.doc_id === docId) { setSelectedDoc(null); setActiveCitation(null); }
    reload();
  };

  const handleCitationClick = (citation) => {
    const doc = docs.find((d) => d.doc_id === citation.doc_id);
    if (doc) {
      setSelectedDoc(doc);
      setTimeout(() => setActiveCitation(citation.chunk_id), 80);
    }
  };

  // ── offline gate ────────────────────────────────────────────────────────────
  if (backendStatus !== "ready") {
    return (
      <OfflineLoader
        status={backendStatus}
        onRetry={() => {
          setBackendStatus("connecting");
          checkHealth().then((ok) => {
            if (ok) reload();
          });
        }}
      />
    );
  }

  // ── graph page ──────────────────────────────────────────────────────────────
  if (page === "graph") {
    return (
      <GraphPage
        docs={docs}
        onBack={() => setPage("main")}
      />
    );
  }

  // ── main page ───────────────────────────────────────────────────────────────
  return (
    <div className="app">
      <header className="header">
        <div className="header__brand">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#6366F1" strokeWidth="2">
            <polygon points="12 2 2 7 12 12 22 7 12 2"/>
            <polyline points="2 17 12 22 22 17"/>
            <polyline points="2 12 12 17 22 12"/>
          </svg>
          <span className="header__title">DocSearch</span>
          <span className="header__pill">Hybrid Knowledge Base</span>
        </div>

        <button
          className="header__graph-btn"
          onClick={() => setPage("graph")}
          title="Explore the knowledge graph"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="5"  cy="12" r="2"/>
            <circle cx="19" cy="5"  r="2"/>
            <circle cx="19" cy="19" r="2"/>
            <line x1="7" y1="11" x2="17" y2="6"/>
            <line x1="7" y1="13" x2="17" y2="18"/>
          </svg>
          Knowledge Graph
        </button>

        <StatsBar stats={stats} health={health} />
      </header>

      <div className="body">
        <aside className="sidebar">
          <section className="sidebar__section">
            <div className="panel-title">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                <polyline points="17 8 12 3 7 8"/>
                <line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
              Upload Document
            </div>
            <div className="sidebar__pad">
              <UploadPanel onUploaded={handleUploaded} />
            </div>
          </section>

          <div className="sidebar__tabs">
            <button
              className={`sidebar__tab${sidebarTab === "docs" ? " sidebar__tab--active" : ""}`}
              onClick={() => setSidebarTab("docs")}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
              Documents
              {docs.length > 0 && <span className="sidebar__tab-count">{docs.length}</span>}
            </button>
            <button
              className={`sidebar__tab${sidebarTab === "search" ? " sidebar__tab--active" : ""}`}
              onClick={() => setSidebarTab("search")}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="11" cy="11" r="8"/>
                <line x1="21" y1="21" x2="16.65" y2="16.65"/>
              </svg>
              Search
            </button>
          </div>

          <div className="sidebar__tab-body">
            {sidebarTab === "docs" ? (
              <div className="sidebar__pad">
                <DocumentList
                  docs={docs}
                  selectedDocId={selectedDoc?.doc_id}
                  onSelect={(d) => { setSelectedDoc(d); setActiveCitation(null); }}
                  onDelete={handleDelete}
                />
              </div>
            ) : (
              <div className="sidebar__pad sidebar__pad--search">
                <SearchPanel onCitationClick={handleCitationClick} />
              </div>
            )}
          </div>
        </aside>

        <main className="center">
          <DocumentViewer doc={selectedDoc} activeCitationChunkId={activeCitationChunkId} />
        </main>

        <aside className="chat-col">
          <div className="panel-title">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
            </svg>
            Chat
            <span className="panel-title__right" style={{ fontSize: 10, color: "var(--text-3)" }}>
              Click citations → jump to source
            </span>
          </div>
          <ChatBox onCitationClick={handleCitationClick} />
        </aside>
      </div>
    </div>
  );
}