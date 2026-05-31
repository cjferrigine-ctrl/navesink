#!/usr/bin/env python3
"""
Navesink ingestion pipeline — reads PDFs from a town corpus/, chunks them,
generates embeddings, and upserts everything into a Pinecone index.

Run with:
  python ingest.py                   # defaults to Red Bank
  python ingest.py --town fairhaven
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import pdfplumber
import pypdfium2 as pdfium
import pytesseract
import tiktoken
from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec

load_dotenv()

# ── Fixed settings (not town-specific) ────────────────────────────────────────
EMBED_MODEL   = "text-embedding-3-small"
EMBED_DIM     = 1536
CHUNK_TOKENS  = 500
OVERLAP       = 50
OCR_THRESHOLD = 50    # characters; pages below this trigger OCR
EMBED_BATCH   = 50    # texts per OpenAI call
UPSERT_BATCH  = 100   # vectors per Pinecone call
CONFIG_DIR    = Path(__file__).parent / "config"

# ── Config loader ──────────────────────────────────────────────────────────────
def load_config(town: str) -> dict:
    path = CONFIG_DIR / f"{town}.json"
    if not path.exists():
        available = [p.stem for p in CONFIG_DIR.glob("*.json")]
        sys.exit(
            f"ERROR: No config found for '{town}'. "
            f"Available towns: {', '.join(sorted(available))}"
        )
    with path.open() as f:
        return json.load(f)

# ── Document-type detection from filename ─────────────────────────────────────
_TYPE_RULES = [
    ("zoning",        re.compile(r"zon|ordinance",             re.I)),
    ("master_plan",   re.compile(r"master.?plan",              re.I)),
    ("historic",      re.compile(r"historic|preservation|hpc", re.I)),
    ("board_minutes", re.compile(r"minutes|meeting|agenda|board", re.I)),
    ("fee_schedule",  re.compile(r"fee|schedule|rate|tariff",  re.I)),
]

def detect_doc_type(filename: str) -> str:
    stem = Path(filename).stem
    for label, pattern in _TYPE_RULES:
        if pattern.search(stem):
            return label
    return "other"

# ── Section-header detection ───────────────────────────────────────────────────
_HEADER_RE = re.compile(
    r"^\s*("
    r"ARTICLE\s+[IVXLCDM\d]+\b[^\n]*|"
    r"CHAPTER\s+\d+\b[^\n]*|"
    r"Section\s+[\d.]+\s+[^\n]+|"
    r"§\s*[\d.\-]+\s+[^\n]+|"
    r"\d+\.\d+\s+[A-Z][^\n]+"
    r")\s*$",
    re.MULTILINE,
)

def _find_headers(text: str) -> list[tuple[int, str]]:
    return [(m.start(), m.group(1).strip()) for m in _HEADER_RE.finditer(text)]

# ── Tokenizer (shared instance) ────────────────────────────────────────────────
_enc = tiktoken.get_encoding("cl100k_base")

# ── Chunking ───────────────────────────────────────────────────────────────────
def make_chunks(
    text: str, filename: str, page_num: int, doc_type: str
) -> list[dict]:
    tokens = _enc.encode(text)
    if not tokens:
        return []

    headers = _find_headers(text)
    chunks: list[dict] = []
    start = 0
    chunk_idx = 0

    while start < len(tokens):
        end = min(start + CHUNK_TOKENS, len(tokens))
        chunk_tokens = tokens[start:end]
        chunk_text = _enc.decode(chunk_tokens)

        char_offset = len(_enc.decode(tokens[:start])) if start else 0

        section_header = ""
        for pos, hdr in headers:
            if pos <= char_offset:
                section_header = hdr
            else:
                break

        vector_id = hashlib.md5(
            f"{filename}|{page_num}|{chunk_idx}".encode()
        ).hexdigest()

        chunks.append({
            "id": vector_id,
            "text": chunk_text,
            "metadata": {
                "source":         filename,
                "page":           page_num,
                "chunk_index":    chunk_idx,
                "doc_type":       doc_type,
                "section_header": section_header,
                "text":           chunk_text[:1000],
            },
        })

        chunk_idx += 1
        if end >= len(tokens):
            break
        start = end - OVERLAP

    return chunks

# ── ecode360 print-header pattern (appears on every page of FairHavenCode.pdf) ─
_ECODE360_HEADER_RE = re.compile(
    r"^Borough of Fair Haven,?\s*NJ\s*[-–]\s*Borough of Fair Haven,?\s*NJ\s*"
    r"https?://\S+\s*",
    re.MULTILINE,
)

def _strip_ecode360_header(text: str) -> str:
    return _ECODE360_HEADER_RE.sub("", text).lstrip()


# ── Serialize a pdfplumber table into structured prose lines ──────────────────
def _table_to_prose(table_data: list[list]) -> str:
    """
    Convert a 2-D table (list of rows from pdfplumber extract_table) into
    structured prose that preserves row/column relationships for embedding.

    Strategy:
      - Last non-empty row that looks like a header (mostly short strings,
        no digits-only cells) becomes the column-name row.
      - Each subsequent data row is serialized as
        "ColA: val | ColB: val | ..." skipping None/empty cells.
      - If no header row is detected, fall back to positional labels.
    """
    if not table_data:
        return ""

    # Reverse rows if every text cell appears to be character-reversed
    # (heuristic: majority of alpha tokens read backwards are real English words)
    def _looks_reversed(row: list) -> bool:
        tokens = []
        for cell in row:
            if cell:
                tokens.extend(str(cell).split())
        if not tokens:
            return False
        rev_hits = sum(1 for t in tokens if t[::-1].isalpha() and len(t) > 3)
        return rev_hits > len(tokens) * 0.5

    # Check first non-empty row
    sample_rows = [r for r in table_data if any(c for c in r)][:3]
    reversed_pdf = any(_looks_reversed(r) for r in sample_rows)

    def _fix(cell) -> str:
        if cell is None:
            return ""
        s = str(cell).strip()
        if reversed_pdf:
            # Reverse each whitespace-separated token individually, then
            # re-join — this handles multi-word cells like "mumixaM erauqs("
            s = " ".join(tok[::-1] for tok in s.split())
        # Normalise internal whitespace / newlines
        return re.sub(r"\s+", " ", s).strip()

    # Find header row: last row where most cells are non-numeric short strings
    header_idx = None
    for i in range(len(table_data) - 1, -1, -1):
        row = [_fix(c) for c in table_data[i]]
        non_empty = [c for c in row if c]
        if not non_empty:
            continue
        digit_only = sum(1 for c in non_empty if re.fullmatch(r"[\d,\.%\-/()N/A]+", c))
        if digit_only / len(non_empty) < 0.4:
            header_idx = i
            break

    if header_idx is not None:
        headers = [_fix(c) for c in table_data[header_idx]]
        data_rows = [
            r for i, r in enumerate(table_data)
            if i != header_idx and any(c for c in r)
        ]
    else:
        headers = [f"Col{j+1}" for j in range(len(table_data[0]))]
        data_rows = [r for r in table_data if any(c for c in r)]

    lines = []
    # Carry forward None cells from merged header columns
    filled_headers = []
    last = ""
    for h in headers:
        last = h if h else last
        filled_headers.append(last)

    for row in data_rows:
        fixed = [_fix(c) for c in row]
        # Carry forward row-span labels in first two columns
        parts = []
        for h, v in zip(filled_headers, fixed):
            if v and v != h:
                label = h if h else ""
                parts.append(f"{label}: {v}" if label else v)
        if parts:
            lines.append(" | ".join(parts))

    return "\n".join(lines)


# ── PDF text extraction with OCR fallback ─────────────────────────────────────
def extract_page_text(pdf_path: Path, page, page_num: int) -> str:
    # For pages where pdfplumber detects table structure, use extract_table()
    # which preserves row/column relationships better than extract_text().
    tables = page.find_tables()
    if tables:
        prose_parts = []
        for tbl in tables:
            data = tbl.extract()
            prose = _table_to_prose(data)
            if prose.strip():
                prose_parts.append(prose)
        # Also grab any non-table text on the page (headings, footnotes)
        raw_text = page.extract_text() or ""
        raw_text = _strip_ecode360_header(raw_text)
        if raw_text.strip():
            prose_parts.append(raw_text)
        combined = "\n\n".join(prose_parts)
        if len(combined.strip()) >= OCR_THRESHOLD:
            return combined

    text = page.extract_text() or ""
    text = _strip_ecode360_header(text)
    if len(text.strip()) >= OCR_THRESHOLD:
        return text

    try:
        doc = pdfium.PdfDocument(str(pdf_path))
        pg = doc[page_num - 1]
        bitmap = pg.render(scale=300 / 72)
        pil_image = bitmap.to_pil()
        return pytesseract.image_to_string(pil_image)
    except Exception as exc:
        print(f"    [WARN] OCR failed on page {page_num}: {exc}")
        return text

# ── Embeddings with one retry on transient error ───────────────────────────────
def embed_batch(client: OpenAI, texts: list[str]) -> list[list[float]]:
    for attempt in range(2):
        try:
            resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
            return [item.embedding for item in resp.data]
        except Exception as exc:
            if attempt == 0:
                print(f"    [WARN] Embedding error, retrying in 5 s: {exc}")
                time.sleep(5)
            else:
                raise

# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Navesink ingestion pipeline")
    parser.add_argument(
        "--town", default="redbank",
        help="Town config to use (default: redbank). Must match a file in config/."
    )
    args = parser.parse_args()

    cfg        = load_config(args.town)
    town_name  = cfg["town"]
    pdf_dir    = Path(cfg["corpus_dir"])
    index_name = cfg["pinecone_index"]

    openai_key   = os.environ.get("OPENAI_API_KEY", "").strip()
    pinecone_key = os.environ.get("PINECONE_API_KEY", "").strip()
    if not openai_key or not pinecone_key:
        sys.exit("ERROR: OPENAI_API_KEY and PINECONE_API_KEY must be set in your .env file.")

    oai = OpenAI(api_key=openai_key)
    pc  = Pinecone(api_key=pinecone_key)

    existing = [idx.name for idx in pc.list_indexes()]
    if index_name not in existing:
        print(f"Creating Pinecone index '{index_name}' (this takes ~30 seconds)...")
        pc.create_index(
            name=index_name,
            dimension=EMBED_DIM,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        while not pc.describe_index(index_name).status["ready"]:
            time.sleep(2)
        print("  Index ready.\n")

    index = pc.Index(index_name)

    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        sys.exit(f"No PDFs found in {pdf_dir}/  — add your files and re-run.")

    print(f"Town          : {town_name}")
    print(f"Corpus        : {pdf_dir}/")
    print(f"Pinecone index: {index_name}")
    print(f"Found {len(pdf_files)} PDF(s)")
    print("─" * 60)

    total_chunks = 0
    failed: list[tuple[str, str]] = []

    for pdf_idx, pdf_path in enumerate(pdf_files, 1):
        filename = pdf_path.name
        doc_type = detect_doc_type(filename)
        print(f"\n[{pdf_idx}/{len(pdf_files)}] {filename}  (type: {doc_type})")

        try:
            all_chunks: list[dict] = []

            with pdfplumber.open(pdf_path) as pdf:
                n_pages = len(pdf.pages)
                for page_num, page in enumerate(pdf.pages, 1):
                    text = extract_page_text(pdf_path, page, page_num)
                    page_chunks = make_chunks(text, filename, page_num, doc_type)
                    all_chunks.extend(page_chunks)
                    print(
                        f"  Extracting page {page_num}/{n_pages} "
                        f"({len(page_chunks)} chunk(s))        ",
                        end="\r",
                    )

            print(f"  {n_pages} page(s) → {len(all_chunks)} chunks                    ")

            if not all_chunks:
                print("  Skipping — no text extracted.")
                continue

            texts = [c["text"] for c in all_chunks]
            embeddings: list[list[float]] = []
            for i in range(0, len(texts), EMBED_BATCH):
                batch_embs = embed_batch(oai, texts[i : i + EMBED_BATCH])
                embeddings.extend(batch_embs)
                print(
                    f"  Embedding {min(i + EMBED_BATCH, len(texts))}/{len(texts)}",
                    end="\r",
                )
            print(f"  Embeddings done ({len(embeddings)})                    ")

            vectors = [
                {"id": c["id"], "values": emb, "metadata": c["metadata"]}
                for c, emb in zip(all_chunks, embeddings)
            ]
            for i in range(0, len(vectors), UPSERT_BATCH):
                index.upsert(vectors=vectors[i : i + UPSERT_BATCH])
                print(
                    f"  Upserting {min(i + UPSERT_BATCH, len(vectors))}/{len(vectors)}",
                    end="\r",
                )
            print(f"  Upserted {len(vectors)} vectors to Pinecone          ")

            total_chunks += len(all_chunks)

        except Exception as exc:
            print(f"  [FAILED] {exc}")
            failed.append((filename, str(exc)))

    print(f"\n{'═' * 60}")
    print(f"INGESTION COMPLETE — {town_name}")
    print(f"{'═' * 60}")
    print(f"  PDFs processed : {len(pdf_files) - len(failed)} / {len(pdf_files)}")
    print(f"  Chunks created : {total_chunks}")
    print(f"  Pinecone index : {index_name}")

    if failed:
        print(f"\n  Failed files ({len(failed)}):")
        for fname, reason in failed:
            print(f"    • {fname}: {reason}")
    else:
        print("\n  All files processed successfully.")

    print()


if __name__ == "__main__":
    main()
