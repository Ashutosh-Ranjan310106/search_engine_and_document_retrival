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
    timestamp
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
            "description": relation,
            "keywords": relation,
            "source_id": chunk_key,
            "file_path": file_path,
            "timestamp": timestamp
        }
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

            add_node(
                maybe_nodes,
                primary_entity,
                "TableEntity",
                chunk_key,
                file_path,
                timestamp
            )

            table_entity_count += 1

            for col, value in row.items():

                if value is None:
                    continue

                value = str(value).strip()

                if not value:
                    continue

                if value == primary_entity:
                    continue

                add_node(
                    maybe_nodes,
                    value,
                    col,
                    chunk_key,
                    file_path,
                    timestamp
                )

                table_entity_count += 1

                relation = SPECIAL_COLUMNS.get(
                    col,
                    col.lower().replace(" ", "_")
                )

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