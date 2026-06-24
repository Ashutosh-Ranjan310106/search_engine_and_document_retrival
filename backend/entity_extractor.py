"""
entity_extractor.py  –  Fully rule-based, zero-ML replacement.

Dropped heavy dependencies
--------------------------
  - gliner   (transformer NER, pulls torch + safetensors)
  - spacy    (en_core_web_sm can silently use torch)

Replaced with
-------------
  - Keyword/gazetteer matching for NER  (GLiNER replacement)
  - Pure-Python regex sentence splitter  (spaCy .sents replacement)
  - Heuristic subject/verb/object finder  (spaCy dependency replacement)
"""

from collections import defaultdict
import logging
import re

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ship-domain label gazetteer  (replaces GLiNER SHIP_LABELS + model)
# ---------------------------------------------------------------------------

SHIP_LABELS = [
    "Ship", "Vessel", "Equipment", "Tool", "Engine", "Pump", "Valve",
    "Tank", "Generator", "Compressor", "Boiler", "Sensor", "Radar",
    "GPS", "Safety Equipment", "Fire Fighting Equipment", "Spare Part",
    "Procedure", "Failure", "Fault", "Port", "Location", "Company",
    "Manufacturer", "Crew Role", "Department", "System", "Subsystem",
]

# keyword → entity label
# Extend this dict freely; all matching is case-insensitive.
_LABEL_KEYWORDS: dict[str, list[str]] = {
    "Ship":                   ["ship", "vessel", "tanker", "freighter",
                               "bulk carrier", "container ship", "yacht",
                               "tug", "barge", "ferry"],
    "Engine":                 ["engine", "motor", "diesel", "turbine",
                               "propulsion"],
    "Pump":                   ["pump", "centrifugal pump", "bilge pump",
                               "ballast pump", "fuel pump"],
    "Valve":                  ["valve", "gate valve", "ball valve",
                               "check valve", "relief valve", "solenoid"],
    "Tank":                   ["tank", "ballast tank", "fuel tank",
                               "cargo tank", "holding tank", "void space"],
    "Generator":              ["generator", "alternator", "genset",
                               "dynamo"],
    "Compressor":             ["compressor", "air compressor",
                               "refrigeration compressor"],
    "Boiler":                 ["boiler", "steam boiler", "auxiliary boiler"],
    "Sensor":                 ["sensor", "detector", "transducer",
                               "transmitter", "gauge", "meter",
                               "level indicator", "flow meter"],
    "Radar":                  ["radar", "arpa", "ecdis", "ais"],
    "GPS":                    ["gps", "gnss", "positioning system",
                               "navigation system"],
    "Safety Equipment":       ["life jacket", "lifeboat", "life raft",
                               "fire extinguisher", "immersion suit",
                               "epirb", "sart", "pyrotechnic"],
    "Fire Fighting Equipment":["foam monitor", "fire hose", "fire pump",
                               "sprinkler", "co2 system", "halon"],
    "Spare Part":             ["spare part", "spare", "replacement part",
                               "consumable", "gasket", "seal", "bearing",
                               "impeller", "filter"],
    "Procedure":              ["procedure", "checklist", "test procedure",
                               "inspection", "overhaul", "maintenance",
                               "commissioning"],
    "Failure":                ["failure", "breakdown", "malfunction",
                               "defect", "damage", "crack", "corrosion",
                               "wear"],
    "Fault":                  ["fault", "fault code", "alarm", "trip",
                               "error", "warning"],
    "Port":                   ["port", "harbour", "anchorage", "berth",
                               "terminal", "quay", "jetty", "dock"],
    "Location":               ["location", "deck", "compartment", "hold",
                               "engine room", "bridge", "wheelhouse",
                               "accommodation"],
    "Company":                ["company", "corporation", "ltd", "inc",
                               "co.", "group", "authority", "agency",
                               "bureau"],
    "Manufacturer":           ["manufacturer", "maker", "oem", "builder",
                               "fabricator"],
    "Crew Role":              ["captain", "chief engineer", "officer",
                               "engineer", "bosun", "crew", "rating",
                               "superintendent", "inspector", "surveyor"],
    "Department":             ["department", "deck department",
                               "engine department", "catering",
                               "safety department"],
    "System":                 ["system", "cooling system", "lubrication",
                               "hydraulic system", "electrical system",
                               "bilge system", "ballast system",
                               "fuel system", "fire detection"],
    "Subsystem":              ["subsystem", "sub-system", "assembly",
                               "module", "unit", "panel", "circuit"],
    "Equipment":              ["equipment", "apparatus", "instrument",
                               "device", "fitting", "accessory",
                               "component", "tool"],
    "Tool":                   ["tool", "wrench", "spanner", "hammer",
                               "drill", "grinder", "gauge tool"],
    "Vessel":                 ["mv ", "mt ", "ss ", "ms ", "uss ", "hms "],
}

# Pre-build a flat list of (pattern, label) sorted longest-first to prefer
# the most specific match.
_PATTERNS: list[tuple[re.Pattern, str]] = []

for _label, _keywords in _LABEL_KEYWORDS.items():
    for _kw in _keywords:
        _pat = re.compile(r'\b' + re.escape(_kw) + r'\b', re.IGNORECASE)
        _PATTERNS.append((_pat, _label))

# Sort by keyword length descending so "bilge pump" beats "pump"
_PATTERNS.sort(key=lambda x: len(x[0].pattern), reverse=True)


# ---------------------------------------------------------------------------
# GLiNER replacement
# ---------------------------------------------------------------------------

class _RuleBasedNER:
    """Drop-in for GLiNER.predict_entities()."""

    def predict_entities(
        self,
        text: str,
        labels: list[str]           # kept for API compatibility, not used
    ) -> list[dict]:
        """
        Return a list of {"text": ..., "label": ..., "start": ..., "end": ...}
        dicts, one per matched keyword span (duplicates removed).
        """
        results: list[dict] = []
        seen_spans: set[tuple[int, int]] = set()

        for pattern, label in _PATTERNS:
            for m in pattern.finditer(text):
                span = (m.start(), m.end())
                # Skip if this span (or a superset) was already claimed
                if any(
                    s <= span[0] and span[1] <= e
                    for s, e in seen_spans
                ):
                    continue
                seen_spans.add(span)
                results.append({
                    "text":  m.group().strip(),
                    "label": label,
                    "start": m.start(),
                    "end":   m.end(),
                })

        return results


ner_model = _RuleBasedNER()


# ---------------------------------------------------------------------------
# spaCy replacement  –  sentence splitter + heuristic SVO extractor
# ---------------------------------------------------------------------------

# Sentence boundary: split on '.', '!', '?' followed by whitespace+capital
# or end-of-string.
_SENT_BOUNDARY = re.compile(r'(?<=[.!?])\s+(?=[A-Z])')

# Very lightweight verb detector: common maritime/engineering verbs +
# any past-tense -ed / gerund -ing word (crude but zero-dependency).
_VERB_RE = re.compile(
    r'\b('
    r'is|are|was|were|has|have|had|did|do|does|be|been|being'
    r'|installed|connected|tested|checked|operated|detected|failed'
    r'|started|stopped|running|leaking|damaged|repaired|replaced'
    r'|activated|deactivated|tripped|alarmed|monitored|controlled'
    r'|supplied|discharged|pumped|pressurised|pressurized'
    r'|contain|contains|contained|provide|provides|provided'
    r'|indicate|indicates|indicated|measure|measures|measured'
    r'|[a-z]+ed|[a-z]+ing'          # catch-all for regular verbs
    r')\b',
    re.IGNORECASE,
)

# Heuristic: nouns are capitalised words or known entity names.
_NOUN_RE = re.compile(r'\b[A-Z][a-zA-Z0-9\-]+\b')


class _Sentence:
    """Mimics a spaCy Span enough for the code below."""
    def __init__(self, text: str):
        self.text = text
        self._tokens = self._tokenise(text)

    # ------------------------------------------------------------------
    # public interface used by extract_rule_entities
    # ------------------------------------------------------------------

    @property
    def sents(self):
        """Yield self (a single sentence object behaves as its own sent)."""
        yield self

    # Expose .text only; the caller iterates doc.sents and uses sent.text

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _tokenise(text: str) -> list[dict]:
        """
        Return a list of token dicts with keys:
          text, pos_, dep_, children (list of child token dicts)

        This is a *very* rough heuristic — sufficient to find VERB→SUBJ/OBJ
        dependency pairs for co-occurrence.
        """
        words = text.split()
        tokens = []
        for w in words:
            pos = "VERB" if _VERB_RE.fullmatch(w.strip(".,;:!?()")) else "NOUN"
            tokens.append({
                "text":     w.strip(".,;:!?()"),
                "pos_":     pos,
                "dep_":     "",
                "children": [],
            })
        return tokens

    def __iter__(self):
        return iter(self._TokenWrapper(t) for t in self._tokens)


class _TokenWrapper:
    """Wraps a raw token dict so callers can do token.pos_, token.children etc."""
    def __init__(self, d: dict):
        self.text     = d["text"]
        self.pos_     = d["pos_"]
        self.dep_     = d["dep_"]
        self.lemma_   = d["text"].lower().rstrip("edingsn")   # crude lemma
        self.children = []   # we don't build a real dep-tree; left empty


class _Doc:
    """Mimics a spaCy Doc: iterable of sentences."""
    def __init__(self, text: str):
        self._text = text
        raw_sents = _SENT_BOUNDARY.split(text) or [text]
        self._sents = [_Sentence(s) for s in raw_sents if s.strip()]

    @property
    def sents(self):
        yield from self._sents


class _RuleBasedNLP:
    """Drop-in for spacy.load('en_core_web_sm')."""

    def __call__(self, text: str) -> _Doc:
        return _Doc(text)


nlp = _RuleBasedNLP()


# ---------------------------------------------------------------------------
# Everything below this line is UNCHANGED from the original
# ---------------------------------------------------------------------------

SPECIAL_COLUMNS = {
    "Acceptance Criteria": "acceptance_criteria",
    "Actual Result":       "actual_result",
    "Status":              "status",
    "Manufacturer":        "manufacturer",
    "Location":            "location",
    "Equipment":           "equipment",
    "Tag Number":          "tag_number",
    "Serial Number":       "serial_number",
}

LONG_TEXT_THRESHOLD = 5


def add_node(maybe_nodes, name, entity_type, chunk_key, file_path, timestamp):
    if not name:
        return
    maybe_nodes[name].append({
        "entity_name": name,
        "entity_type": entity_type,
        "description": name,
        "source_id":   chunk_key,
        "file_path":   file_path,
        "timestamp":   timestamp,
    })


def add_edge(
    maybe_edges, src, tgt, relation,
    chunk_key, file_path, timestamp, description=None
):
    if not src or not tgt:
        return
    if src == tgt:
        return
    edge_key = (src, tgt)
    maybe_edges[edge_key].append({
        "src_id":      src,
        "tgt_id":      tgt,
        "weight":      1.0,
        "description": description if description is not None else relation,
        "keywords":    relation,
        "source_id":   chunk_key,
        "file_path":   file_path,
        "timestamp":   timestamp,
    })


def _col_to_relation(col):
    return SPECIAL_COLUMNS.get(
        col, col.strip().lower().replace(" ", "_")
    )


def _is_numeric_only(value):
    return not any(ch.isalpha() for ch in value)


def _handle_long_text_cell(
    maybe_nodes, maybe_edges, primary_entity,
    col, value, chunk_key, file_path, timestamp
):
    col_relation = _col_to_relation(col)
    raw_entities = ner_model.predict_entities(value, SHIP_LABELS)

    seen: set[str] = set()
    unique_entities = []
    for ent in raw_entities:
        ent_name = ent["text"].strip()
        if ent_name and ent_name not in seen:
            seen.add(ent_name)
            unique_entities.append(ent)

    if unique_entities:
        relation = f"mentioned_in_{col_relation}"
        for ent in unique_entities:
            ent_name = ent["text"].strip()
            add_node(maybe_nodes, ent_name, ent["label"],
                     chunk_key, file_path, timestamp)
            add_edge(maybe_edges, primary_entity, ent_name,
                     relation, chunk_key, file_path, timestamp)
        logger.debug(
            f"[TABLE][LONG] col={col!r} → "
            f"{len(unique_entities)} rule-NER entities via {relation!r}"
        )
    else:
        fallback_entity = col.strip()
        relation = f"has_{col_relation}"
        add_node(maybe_nodes, fallback_entity, col,
                 chunk_key, file_path, timestamp)
        add_edge(maybe_edges, primary_entity, fallback_entity,
                 relation, chunk_key, file_path, timestamp,
                 description=value)
        logger.debug(
            f"[TABLE][LONG] col={col!r} → no entities; "
            f"fallback node={fallback_entity!r} via {relation!r}"
        )


def extract_rule_entities(
    text, chunk_key, file_path, timestamp, table_data=None
):
    maybe_nodes = defaultdict(list)
    maybe_edges = defaultdict(list)
    logger.info(f"[ENTITY] Processing chunk={chunk_key}")

    # =========================================================
    # TABLE EXTRACTION
    # =========================================================
    table_entity_count  = 0
    table_relation_count = 0

    if table_data:
        logger.info(f"[TABLE] Found {len(table_data)} rows")
        print(f"[TABLE] Found {len(table_data)} rows")

        for row in table_data:
            if not isinstance(row, dict):
                continue

            primary_entity = None
            for key, value in row.items():
                if value is None:
                    continue
                value = str(value).strip()
                if value:
                    primary_entity = value
                    break

            if not primary_entity:
                continue

            add_node(maybe_nodes, primary_entity, "TableEntity",
                     chunk_key, file_path, timestamp)
            table_entity_count += 1

            for col, value in row.items():
                if value is None:
                    continue
                value = str(value).strip()
                if not value or value == primary_entity:
                    continue
                if _is_numeric_only(value):
                    logger.debug(
                        f"[TABLE] Skipping numeric-only cell "
                        f"col={col!r} value={value!r}"
                    )
                    continue

                if len(value) <= LONG_TEXT_THRESHOLD:
                    add_node(maybe_nodes, value, col,
                             chunk_key, file_path, timestamp)
                    table_entity_count += 1
                    add_edge(maybe_edges, primary_entity, value,
                             _col_to_relation(col),
                             chunk_key, file_path, timestamp)
                    table_relation_count += 1
                else:
                    before_nodes = len(maybe_nodes)
                    before_edges = len(maybe_edges)
                    _handle_long_text_cell(
                        maybe_nodes, maybe_edges, primary_entity,
                        col, value, chunk_key, file_path, timestamp
                    )
                    table_entity_count   += len(maybe_nodes) - before_nodes
                    table_relation_count += len(maybe_edges) - before_edges

    logger.info(
        f"[TABLE] Extracted "
        f"{table_entity_count} entities "
        f"{table_relation_count} relations"
    )

    # =========================================================
    # RULE-BASED NER  (was: GLiNER)
    # =========================================================
    entities = ner_model.predict_entities(text, SHIP_LABELS)
    logger.info(f"[RULE-NER] Found {len(entities)} entities")

    entity_lookup: dict[str, dict] = {}
    for ent in entities:
        entity_name = ent["text"].strip()
        entity_lookup[entity_name] = ent
        add_node(maybe_nodes, entity_name, ent["label"],
                 chunk_key, file_path, timestamp)

    # =========================================================
    # HEURISTIC RELATIONS  (was: spaCy dependency parse)
    # =========================================================
    doc = nlp(text)
    relation_count = 0

    for sent in doc.sents:
        sent_entities = [
            name for name in entity_lookup
            if name.lower() in sent.text.lower()
        ]
        if len(sent_entities) < 2:
            continue

        for token in sent:
            if token.pos_ != "VERB":
                continue

            # Without a real dep-tree we cannot reliably find nsubj/dobj,
            # so we collect nouns *adjacent* to the verb as proxies.
            words = sent.text.split()
            try:
                vi = words.index(token.text)
            except ValueError:
                continue

            window = words[max(0, vi - 3): vi] + words[vi + 1: vi + 4]
            subjects = [
                e for e in sent_entities
                if any(w.lower() in e.lower() for w in window[:3])
            ]
            objects = [
                e for e in sent_entities
                if any(w.lower() in e.lower() for w in window[3:])
            ]

            for src in subjects:
                for tgt in objects:
                    if src not in maybe_nodes or tgt not in maybe_nodes:
                        continue
                    add_edge(maybe_edges, src, tgt, token.lemma_,
                             chunk_key, file_path, timestamp)
                    relation_count += 1

    # =========================================================
    # CO-OCCURRENCE RELATIONS  (unchanged logic)
    # =========================================================
    cooccur_count = 0

    for sent in doc.sents:
        sent_entities = [
            name for name in entity_lookup
            if name.lower() in sent.text.lower()
        ]
        if len(sent_entities) < 2:
            continue

        for i in range(len(sent_entities)):
            for j in range(i + 1, len(sent_entities)):
                add_edge(
                    maybe_edges,
                    sent_entities[i], sent_entities[j],
                    "associated_with",
                    chunk_key, file_path, timestamp,
                )
                cooccur_count += 1

    logger.info(
        f"[RELATIONS] Dependency={relation_count} "
        f"CoOccurrence={cooccur_count}"
    )
    logger.info(
        f"[FINAL] Nodes={len(maybe_nodes)} Edges={len(maybe_edges)}"
    )

    return dict(maybe_nodes), dict(maybe_edges)