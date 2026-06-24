from collections import defaultdict
import logging
import spacy
from gliner import GLiNER

logger = logging.getLogger(__name__)

nlp = spacy.load("en_core_web_sm")

ner_model = GLiNER.from_pretrained(
    "urchade/gliner_medium-v2.1"
)

SHIP_LABELS = [
    "Ship",
    "Vessel",
    "Equipment",
    "Tool",
    "Engine",
    "Pump",
    "Valve",
    "Tank",
    "Generator",
    "Compressor",
    "Boiler",
    "Sensor",
    "Radar",
    "GPS",
    "Safety Equipment",
    "Fire Fighting Equipment",
    "Spare Part",
    "Procedure",
    "Failure",
    "Fault",
    "Port",
    "Location",
    "Company",
    "Manufacturer",
    "Crew Role",
    "Department",
    "System",
    "Subsystem"
]

SPECIAL_COLUMNS = {
    "Acceptance Criteria": "acceptance_criteria",
    "Actual Result": "actual_result",
    "Status": "status",
    "Manufacturer": "manufacturer",
    "Location": "location",
    "Equipment": "equipment",
    "Tag Number": "tag_number",
    "Serial Number": "serial_number"
}

# Cell values longer than this (in characters) are treated as free-text
# paragraphs rather than atomic entity names.
LONG_TEXT_THRESHOLD = 5


def add_node(
    maybe_nodes,
    name,
    entity_type,
    chunk_key,
    file_path,
    timestamp
):
    if not name:
        return

    maybe_nodes[name].append(
        {
            "entity_name": name,
            "entity_type": entity_type,
            "description": name,
            "source_id": chunk_key,
            "file_path": file_path,
            "timestamp": timestamp
        }
    )


def add_edge(
    maybe_edges,
    src,
    tgt,
    relation,
    chunk_key,
    file_path,
    timestamp,
    description=None
):
    if not src or not tgt:
        return

    if src == tgt:
        return

    edge_key = (src, tgt)

    maybe_edges[edge_key].append(
        {
            "src_id": src,
            "tgt_id": tgt,
            "weight": 1.0,
            "description": description if description is not None else relation,
            "keywords": relation,
            "source_id": chunk_key,
            "file_path": file_path,
            "timestamp": timestamp
        }
    )


def _col_to_relation(col):
    """Normalise a column header into a snake_case relation name."""
    return SPECIAL_COLUMNS.get(
        col,
        col.strip().lower().replace(" ", "_")
    )


def _is_numeric_only(value):
    """
    Return True when *value* contains no alphabetic characters at all —
    i.e. it is a pure number, date-like token, unit string, or any other
    value that carries no meaningful entity name.

    Examples that return True  → "42", "3.14", "001", "-7", "2024-01-15"
    Examples that return False → "PS-101", "5 bar", "Pump 3", "N/A"
    """
    return not any(ch.isalpha() for ch in value)


def _handle_long_text_cell(
    maybe_nodes,
    maybe_edges,
    primary_entity,
    col,
    value,
    chunk_key,
    file_path,
    timestamp
):
    """
    Process a table cell whose value exceeds LONG_TEXT_THRESHOLD.

    Strategy
    --------
    1. Run GLiNER on the cell text.
    2. If entities found  → create nodes for each unique entity and link them
       to the primary row entity via  mentioned_in_<col>  relations.
    3. If no entities found → create a single fallback node from the column
       header and link it via  has_<col>,  storing the original paragraph in
       the edge description.
    """
    col_relation = _col_to_relation(col)

    # --- GLiNER extraction ---------------------------------------------------
    raw_entities = ner_model.predict_entities(value, SHIP_LABELS)

    # Deduplicate by entity text (case-sensitive, preserving first occurrence)
    seen = set()
    unique_entities = []
    for ent in raw_entities:
        ent_name = ent["text"].strip()
        if ent_name and ent_name not in seen:
            seen.add(ent_name)
            unique_entities.append(ent)

    if unique_entities:
        # ----- path A: GLiNER found entities ---------------------------------
        relation = f"mentioned_in_{col_relation}"

        for ent in unique_entities:
            ent_name = ent["text"].strip()

            add_node(
                maybe_nodes,
                ent_name,
                ent["label"],
                chunk_key,
                file_path,
                timestamp
            )

            add_edge(
                maybe_edges,
                primary_entity,
                ent_name,
                relation,
                chunk_key,
                file_path,
                timestamp
            )

        logger.debug(
            f"[TABLE][LONG] col={col!r} → "
            f"{len(unique_entities)} GLiNER entities "
            f"linked via {relation!r}"
        )

    else:
        # ----- path B: no GLiNER entities → fallback to column header --------
        fallback_entity = col.strip()
        relation = f"has_{col_relation}"

        add_node(
            maybe_nodes,
            fallback_entity,
            col,
            chunk_key,
            file_path,
            timestamp
        )

        # Store the original paragraph in the edge description so the
        # information is not lost even though no node was created for it.
        add_edge(
            maybe_edges,
            primary_entity,
            fallback_entity,
            relation,
            chunk_key,
            file_path,
            timestamp,
            description=value          # ← paragraph preserved in metadata
        )

        logger.debug(
            f"[TABLE][LONG] col={col!r} → "
            f"no GLiNER entities; fallback node={fallback_entity!r} "
            f"via {relation!r}"
        )


def extract_rule_entities(
    text,
    chunk_key,
    file_path,
    timestamp,
    table_data=None
):
    maybe_nodes = defaultdict(list)
    maybe_edges = defaultdict(list)
    logger.info(
        f"[ENTITY] Processing chunk={chunk_key}"
    )

    # =====================================================
    # TABLE EXTRACTION
    # =====================================================
    table_entity_count = 0
    table_relation_count = 0

    if table_data:

        logger.info(
            f"[TABLE] Found {len(table_data)} rows"
        )
        print(
            f"[TABLE] Found {len(table_data)} rows"
        )

        for row in table_data:

            if not isinstance(row, dict):
                continue

            # ------------------------------------------------------------------
            # Determine the primary entity for this row (first non-empty cell).
            # ------------------------------------------------------------------
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

            # The primary entity is always added as a compact node regardless
            # of its length (it is the row anchor).
            add_node(
                maybe_nodes,
                primary_entity,
                "TableEntity",
                chunk_key,
                file_path,
                timestamp
            )

            table_entity_count += 1

            # ------------------------------------------------------------------
            # Process every other cell in the row.
            # ------------------------------------------------------------------
            for col, value in row.items():

                if value is None:
                    continue

                value = str(value).strip()

                if not value:
                    continue

                if value == primary_entity:
                    continue

                # Skip cells that are pure numbers / dates / codes with no
                # alphabetic content — they produce meaningless graph nodes.
                if _is_numeric_only(value):
                    logger.debug(
                        f"[TABLE] Skipping numeric-only cell "
                        f"col={col!r} value={value!r}"
                    )
                    continue

                is_long_text = len(value) > LONG_TEXT_THRESHOLD

                if not is_long_text:
                    # ----------------------------------------------------------
                    # Short value → existing behaviour: node + direct relation.
                    # ----------------------------------------------------------
                    add_node(
                        maybe_nodes,
                        value,
                        col,
                        chunk_key,
                        file_path,
                        timestamp
                    )

                    table_entity_count += 1

                    relation = _col_to_relation(col)

                    add_edge(
                        maybe_edges,
                        primary_entity,
                        value,
                        relation,
                        chunk_key,
                        file_path,
                        timestamp
                    )

                    table_relation_count += 1

                else:
                    # ----------------------------------------------------------
                    # Long value → GLiNER extraction or fallback.
                    # ----------------------------------------------------------
                    before_nodes = len(maybe_nodes)
                    before_edges = len(maybe_edges)

                    _handle_long_text_cell(
                        maybe_nodes,
                        maybe_edges,
                        primary_entity,
                        col,
                        value,
                        chunk_key,
                        file_path,
                        timestamp
                    )

                    table_entity_count  += len(maybe_nodes) - before_nodes
                    table_relation_count += len(maybe_edges) - before_edges

    logger.info(
        f"[TABLE] Extracted "
        f"{table_entity_count} entities "
        f"{table_relation_count} relations"
    )

    # =====================================================
    # GLINER NER
    # =====================================================

    entities = ner_model.predict_entities(
        text,
        SHIP_LABELS
    )

    logger.info(
        f"[GLINER] Found {len(entities)} entities"
    )

    entity_lookup = {}

    for ent in entities:

        entity_name = ent["text"].strip()

        entity_lookup[entity_name] = ent

        add_node(
            maybe_nodes,
            entity_name,
            ent["label"],
            chunk_key,
            file_path,
            timestamp
        )

    # =====================================================
    # SPACY RELATIONS
    # =====================================================

    doc = nlp(text)

    relation_count = 0

    for sent in doc.sents:

        sent_entities = []

        sent_text_lower = sent.text.lower()

        for ent_name in entity_lookup:

            if ent_name.lower() in sent_text_lower:
                sent_entities.append(ent_name)

        if len(sent_entities) < 2:
            continue

        for token in sent:

            if token.pos_ != "VERB":
                continue

            subjects = []

            objects = []

            for child in token.children:

                if child.dep_ in (
                    "nsubj",
                    "nsubjpass"
                ):
                    subjects.append(child.text)

                elif child.dep_ in (
                    "dobj",
                    "obj",
                    "attr",
                    "pobj"
                ):
                    objects.append(child.text)

            for src in subjects:
                for tgt in objects:

                    if src not in maybe_nodes:
                        continue

                    if tgt not in maybe_nodes:
                        continue

                    add_edge(
                        maybe_edges,
                        src,
                        tgt,
                        token.lemma_,
                        chunk_key,
                        file_path,
                        timestamp
                    )

                    relation_count += 1

    # =====================================================
    # CO-OCCURRENCE RELATIONS
    # =====================================================

    cooccur_count = 0

    for sent in doc.sents:

        sent_entities = []

        sent_text_lower = sent.text.lower()

        for ent_name in entity_lookup:

            if ent_name.lower() in sent_text_lower:
                sent_entities.append(ent_name)

        if len(sent_entities) < 2:
            continue

        for i in range(len(sent_entities)):

            for j in range(i + 1, len(sent_entities)):

                src = sent_entities[i]
                tgt = sent_entities[j]

                add_edge(
                    maybe_edges,
                    src,
                    tgt,
                    "associated_with",
                    chunk_key,
                    file_path,
                    timestamp
                )

                cooccur_count += 1

    logger.info(
        f"[RELATIONS] Dependency={relation_count} "
        f"CoOccurrence={cooccur_count}"
    )

    logger.info(
        f"[FINAL] Nodes={len(maybe_nodes)} "
        f"Edges={len(maybe_edges)}"
    )

    return (
        dict(maybe_nodes),
        dict(maybe_edges)
    )