import "./StatsBar.css";

const STATS = [
  { key: "documents",    label: "Docs"      },
  { key: "chunks",       label: "Chunks"    },
  { key: "total_chars",  label: "Chars",    fmt: (v) => `${(v / 1000).toFixed(1)}K` },
];

const FEATURES = [
  { key: "sentence_transformers", label: "Embeddings", on: "Semantic", off: "Random" },
  { key: "spacy_ner",             label: "NER",        on: "spaCy",    off: "Regex"  },
  { key: "llm",                   label: "LLM",        on: "ollama",   off: "None"   },
];

export default function StatsBar({ stats }) {
  if (!stats) return <div className="stats-bar stats-bar--loading" />;

  return (
    <div className="stats-bar">
      {STATS.map(({ key, label, fmt }) => (
        <div key={key} className="stat">
          <span className="stat__val">{fmt ? fmt(stats[key] ?? 0) : (stats[key] ?? 0)}</span>
          <span className="stat__label">{label}</span>
        </div>
      ))}
      <div className="stat stat--divider" />
      {FEATURES.map(({ key, label, on, off }) => {
        const active = stats.features?.[key];
        return (
          <div key={key} className="stat">
            <span className={`stat__val stat__val--feature${active ? " stat__val--on" : " stat__val--off"}`}>
              {active ? `✓ ${on}` : off}
            </span>
            <span className="stat__label">{label}</span>
          </div>
        );
      })}
    </div>
  );
}
