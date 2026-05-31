#!/usr/bin/env python3
"""
Diagnose PDF extraction quality in a corpus directory.

Flags:
  - Pages with fewer than 100 chars of extractable text
  - Pages that appear to contain tables (detected via pdfplumber table finder
    AND via text heuristics: multi-space columns, pipe chars, grid patterns)
  - Pages where pdfplumber yields little text but OCR would be needed

Usage:
  python diagnose_corpus.py [--corpus fairhaven_corpus/]
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

# ── Thresholds ────────────────────────────────────────────────────────────────
SPARSE_THRESHOLD   = 100   # chars; below this = sparse / likely image
TABLE_SPACES_RE    = re.compile(r" {3,}")   # 3+ consecutive spaces = column gap
PIPE_ROW_RE        = re.compile(r"\|.+\|")  # pipe-delimited rows
TAB_RE             = re.compile(r"\t")
DIGIT_GRID_RE      = re.compile(r"(\d+[\''\"°]?\s{2,}){3,}")  # repeated measurements


# ── Data classes ─────────────────────────────────────────────────────────────
@dataclass
class PageReport:
    pdf:        str
    page_num:   int
    char_count: int
    flags:      list[str] = field(default_factory=list)
    sample:     str = ""   # first 200 chars of extracted text


@dataclass
class DocReport:
    pdf:        str
    total_pages: int
    sparse_pages:  list[PageReport] = field(default_factory=list)
    table_pages:   list[PageReport] = field(default_factory=list)
    pdfplumber_tables: list[tuple[int, int]] = field(default_factory=list)  # (page, n_tables)


# ── Table detection heuristics ───────────────────────────────────────────────
def text_looks_like_table(text: str) -> list[str]:
    """Return list of triggered heuristics (empty = no table detected)."""
    reasons = []
    if TABLE_SPACES_RE.search(text):
        reasons.append("multi-space column gaps")
    if PIPE_ROW_RE.search(text):
        reasons.append("pipe-delimited rows")
    if TAB_RE.search(text):
        reasons.append("tab characters")
    if DIGIT_GRID_RE.search(text):
        reasons.append("repeated measurement grid")
    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) >= 4:
        # Check if many lines share consistent spacing at same column positions
        space_positions = [
            set(i for i, c in enumerate(ln) if c == " ")
            for ln in lines[:20]
        ]
        if len(space_positions) >= 3:
            common = space_positions[0]
            for sp in space_positions[1:]:
                common &= sp
            if len(common) >= 3:
                reasons.append(f"aligned column whitespace ({len(common)} shared positions)")
    return reasons


# ── Per-PDF analysis ──────────────────────────────────────────────────────────
def analyze_pdf(pdf_path: Path) -> DocReport:
    report = DocReport(pdf=pdf_path.name, total_pages=0)

    with pdfplumber.open(pdf_path) as pdf:
        report.total_pages = len(pdf.pages)

        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            char_count = len(text.strip())

            # --- Check for pdfplumber-detected tables ---
            tables = page.find_tables()
            if tables:
                report.pdfplumber_tables.append((page_num, len(tables)))

            page_report = PageReport(
                pdf=pdf_path.name,
                page_num=page_num,
                char_count=char_count,
                sample=text.strip()[:200].replace("\n", " ↵ "),
            )

            # --- Flag: sparse page ---
            if char_count < SPARSE_THRESHOLD:
                page_report.flags.append(f"SPARSE ({char_count} chars)")
                report.sparse_pages.append(page_report)

            # --- Flag: table-like content ---
            table_reasons = text_looks_like_table(text)
            if table_reasons or tables:
                if tables:
                    table_reasons.insert(0, f"pdfplumber found {len(tables)} table(s)")
                page_report.flags.extend(table_reasons)
                # Only add if not already added via sparse path
                # (a sparse page can also be a table page)
                report.table_pages.append(page_report)

    return report


# ── Formatting helpers ────────────────────────────────────────────────────────
def bar(label: str, width: int = 60) -> str:
    return f"\n{'─' * width}\n{label}\n{'─' * width}"


def print_doc_report(rep: DocReport) -> None:
    sparse_count = len(rep.sparse_pages)
    table_count  = len(rep.table_pages)
    plumber_count = len(rep.pdfplumber_tables)

    status_parts = []
    if sparse_count:
        status_parts.append(f"{sparse_count} sparse")
    if table_count:
        status_parts.append(f"{table_count} table-flagged")
    if plumber_count:
        status_parts.append(f"{plumber_count} pdfplumber-detected tables")
    status = ", ".join(status_parts) if status_parts else "clean"

    print(f"\n{'═' * 70}")
    print(f"  {rep.pdf}")
    print(f"  {rep.total_pages} pages  |  {status}")
    print(f"{'═' * 70}")

    if rep.sparse_pages:
        print(bar("  SPARSE PAGES (< 100 chars extracted — likely image/scan)"))
        for pr in rep.sparse_pages:
            print(f"    p.{pr.page_num:>4}  [{pr.char_count} chars]")
            if pr.sample:
                print(f"           sample: \"{pr.sample[:80]}\"")

    if rep.pdfplumber_tables:
        print(bar("  PDFPLUMBER-DETECTED TABLES"))
        for page_num, n in rep.pdfplumber_tables:
            print(f"    p.{page_num:>4}  {n} table structure(s) found")

    if rep.table_pages:
        print(bar("  TABLE-LIKE TEXT HEURISTICS"))
        for pr in rep.table_pages:
            heuristics = [f for f in pr.flags if "SPARSE" not in f]
            if heuristics:
                print(f"    p.{pr.page_num:>4}  [{pr.char_count} chars]  →  {'; '.join(heuristics)}")
                print(f"           sample: \"{pr.sample[:100]}\"")


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose PDF corpus extraction quality")
    parser.add_argument(
        "--corpus", default="fairhaven_corpus",
        help="Path to corpus directory (default: fairhaven_corpus/)"
    )
    args = parser.parse_args()

    corpus = Path(args.corpus)
    if not corpus.exists():
        sys.exit(f"ERROR: corpus directory '{corpus}' not found")

    pdfs = sorted(corpus.glob("*.pdf"))
    if not pdfs:
        sys.exit(f"ERROR: no PDFs found in '{corpus}'")

    print(f"Diagnosing {len(pdfs)} PDFs in {corpus}/")
    print("This may take a minute for large files...\n")

    all_reports: list[DocReport] = []
    for pdf_path in pdfs:
        print(f"  Scanning {pdf_path.name} ...", flush=True)
        try:
            rep = analyze_pdf(pdf_path)
            all_reports.append(rep)
        except Exception as exc:
            print(f"  [ERROR] {pdf_path.name}: {exc}")

    # ── Per-document detail ───────────────────────────────────────────────────
    print("\n\n" + "═" * 70)
    print("  PER-DOCUMENT DETAIL")
    print("═" * 70)
    for rep in all_reports:
        print_doc_report(rep)

    # ── Summary table ─────────────────────────────────────────────────────────
    print("\n\n" + "═" * 70)
    print("  SUMMARY")
    print("═" * 70)
    print(f"  {'Document':<52} {'Pages':>5}  {'Sparse':>6}  {'Tables':>6}  {'Plumber':>7}")
    print(f"  {'─' * 52} {'─' * 5}  {'─' * 6}  {'─' * 6}  {'─' * 7}")
    total_sparse = 0
    total_table  = 0
    for rep in all_reports:
        name = rep.pdf[:51]
        total_sparse += len(rep.sparse_pages)
        total_table  += len(rep.table_pages)
        print(
            f"  {name:<52} {rep.total_pages:>5}  "
            f"{len(rep.sparse_pages):>6}  "
            f"{len(rep.table_pages):>6}  "
            f"{len(rep.pdfplumber_tables):>7}"
        )
    print(f"  {'─' * 52} {'─' * 5}  {'─' * 6}  {'─' * 6}  {'─' * 7}")
    total_pages = sum(r.total_pages for r in all_reports)
    print(
        f"  {'TOTAL':<52} {total_pages:>5}  "
        f"{total_sparse:>6}  "
        f"{total_table:>6}"
    )

    # ── Critical pages (sparse AND table-related) ─────────────────────────────
    critical: list[PageReport] = []
    for rep in all_reports:
        sparse_nums = {p.page_num for p in rep.sparse_pages}
        table_nums  = {p.page_num for p in rep.table_pages}
        both = sparse_nums & table_nums
        for pr in rep.table_pages:
            if pr.page_num in both:
                critical.append(pr)

    if critical:
        print(f"\n  ⚠  CRITICAL: {len(critical)} page(s) are BOTH sparse AND table-flagged")
        print("     (table data present but extractable text is near-zero)")
        for pr in critical:
            print(f"     • {pr.pdf}  p.{pr.page_num}  ({pr.char_count} chars)")

    print()


if __name__ == "__main__":
    main()
