#!/usr/bin/env python3
"""
Navesink RAG query CLI — ask permitting questions about a configured town.

Run with:
  python query.py                   # defaults to Red Bank
  python query.py --town fairhaven
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone

load_dotenv()

# ── Fixed settings ─────────────────────────────────────────────────────────────
EMBED_MODEL  = "text-embedding-3-small"
CLAUDE_MODEL = "claude-sonnet-4-5"
TOP_K        = 5
CONFIG_DIR   = Path(__file__).parent / "config"

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

# ── Helpers ────────────────────────────────────────────────────────────────────
def embed_question(oai: OpenAI, question: str) -> list[float]:
    resp = oai.embeddings.create(model=EMBED_MODEL, input=question)
    return resp.data[0].embedding


def query_pinecone(index, vector: list[float]) -> list:
    return index.query(vector=vector, top_k=TOP_K, include_metadata=True).matches


def build_context(matches: list) -> str:
    parts = []
    for i, match in enumerate(matches, 1):
        meta    = match.metadata
        source  = meta.get("source", "Unknown")
        page    = meta.get("page", "?")
        section = meta.get("section_header", "")
        text    = meta.get("text", "")

        header = f"[Excerpt {i}]  Source: {source}  |  Page: {page}"
        if section:
            header += f"  |  Section: {section}"
        parts.append(f"{header}\n{text}")

    return "\n\n---\n\n".join(parts)


def ask_claude(
    ac: anthropic.Anthropic, question: str, context: str, system_prompt: str
) -> str:
    user_message = (
        f"Here are the relevant document excerpts:\n\n"
        f"{context}\n\n"
        f"Question: {question}"
    )
    msg = ac.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return msg.content[0].text


# ── Main loop ──────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Navesink permitting assistant")
    parser.add_argument(
        "--town", default="redbank",
        help="Town to query (default: redbank). Must match a file in config/."
    )
    args = parser.parse_args()

    cfg           = load_config(args.town)
    town_name     = cfg["town"]
    state         = cfg["state"]
    index_name    = cfg["pinecone_index"]
    system_prompt = cfg["system_prompt"]

    openai_key    = os.environ.get("OPENAI_API_KEY", "").strip()
    pinecone_key  = os.environ.get("PINECONE_API_KEY", "").strip()
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()

    missing = [name for name, val in [
        ("OPENAI_API_KEY",    openai_key),
        ("PINECONE_API_KEY",  pinecone_key),
        ("ANTHROPIC_API_KEY", anthropic_key),
    ] if not val]
    if missing:
        sys.exit(f"ERROR: Missing environment variables: {', '.join(missing)}")

    oai   = OpenAI(api_key=openai_key)
    pc    = Pinecone(api_key=pinecone_key)
    ac    = anthropic.Anthropic(api_key=anthropic_key)
    index = pc.Index(index_name)

    title = f"Navesink Permitting Assistant — {town_name}, {state}"
    border = "═" * (len(title) + 4)
    print()
    print(f"╔{border}╗")
    print(f"║  {title}  ║")
    print(f"║  {'Powered by Navesink Consulting':<{len(title)}}  ║")
    print(f"╚{border}╝")
    print(f"\nAsk any question about {town_name} permitting, zoning, or")
    print("historic preservation. Type 'quit' to exit.\n")

    while True:
        try:
            question = input("Your question: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if question.lower() in ("quit", "exit", "q"):
            print("Goodbye.")
            break

        if not question:
            continue

        print("\n  Searching documents...", end="", flush=True)
        vector  = embed_question(oai, question)
        matches = query_pinecone(index, vector)
        context = build_context(matches)
        print(" done.")

        print("  Generating answer...\n")

        answer = ask_claude(ac, question, context, system_prompt)

        print("─" * 62)
        print(answer)
        print("─" * 62)
        print()


if __name__ == "__main__":
    main()
