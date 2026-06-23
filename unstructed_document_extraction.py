import tempfile
from pathlib import Path
from bs4 import BeautifulSoup
from unstructured.partition.auto import partition


def html_table_to_records(html: str):
    """
    Convert HTML table to:

    [
        {"Product":"A","Price":"10"},
        {"Product":"B","Price":"15"}
    ]
    """

    soup = BeautifulSoup(html, "html.parser")

    rows = soup.find_all("tr")

    if len(rows) < 2:
        return []

    headers = [
        cell.get_text(" ", strip=True)
        for cell in rows[0].find_all(["th", "td"])
    ]

    records = []

    for row in rows[1:]:

        values = [
            cell.get_text(" ", strip=True)
            for cell in row.find_all(["th", "td"])
        ]

        if not values:
            continue

        if len(values) < len(headers):
            values.extend([""] * (len(headers) - len(values)))

        record = {}

        for i, header in enumerate(headers):
            record[header] = values[i]

        records.append(record)

    return records


def extract_with_unstructured(filename: str, content: bytes):

    suffix = Path(filename).suffix.lower()

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    elements = partition(filename=tmp_path, strategy="hi_res", infer_table_structure=True)

    output = []

    for el in elements:

        category = getattr(el, "category", "Unknown")
        text = getattr(el, "text", "")

        if category == "Table":

            html = None

            if hasattr(el, "metadata"):
                html = getattr(el.metadata, "text_as_html", None)

            if html:

                records = html_table_to_records(html)

                output.append(
                    {
                        "type": "Table",
                        "data": records,
                        "text": str(records)
                    }
                )

            else:

                output.append(
                    {
                        "type": "Table",
                        "text": text
                    }
                )

        else:

            if text.strip():

                output.append(
                    {
                        "type": category,
                        "text": text
                    }
                )

    return output


def chunk_elements(
    elements,
    target_size=1200,
    overlap=150
):
    chunks = []

    current_parts = []
    current_size = 0

    for el in elements:

        text = el.get("text", "").strip()

        if not text:
            continue

        el_type = el.get("type", "")

        # TABLE = standalone chunk
        if el_type == "Table":

            if current_parts:
                chunks.append(
                    {
                        "type": "section",
                        "text": "\n\n".join(current_parts)
                    }
                )

                current_parts = []
                current_size = 0

            chunks.append(
                {
                    "type": "table",
                    "text": text,
                    "data": el.get("data", [])
                }
            )

            continue

        # Very large paragraph
        if len(text) > target_size * 1.5:

            if current_parts:
                chunks.append(
                    {
                        "type": "section",
                        "text": "\n\n".join(current_parts)
                    }
                )

                current_parts = []
                current_size = 0

            start = 0

            while start < len(text):

                end = start + target_size

                chunks.append(
                    {
                        "type": "paragraph",
                        "text": text[start:end]
                    }
                )

                start += target_size - overlap

            continue

        if current_size + len(text) > target_size:

            chunks.append(
                {
                    "type": "section",
                    "text": "\n\n".join(current_parts)
                }
            )

            overlap_text = ""

            if current_parts:

                overlap_text = current_parts[-1][-overlap:]

            current_parts = [overlap_text, text]
            current_size = len(overlap_text) + len(text)

        else:

            current_parts.append(text)
            current_size += len(text)

    if current_parts:

        chunks.append(
            {
                "type": "section",
                "text": "\n\n".join(current_parts)
            }
        )

    return [
        {
            "index": i,
            "type": c["type"],
            "text": c["text"],
            "data": c.get("data")
        }
        for i, c in enumerate(chunks)
    ]