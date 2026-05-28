#!/usr/bin/env python3
"""
Navesink RAG query CLI — ask permitting questions about Red Bank, NJ.
Run with: python query.py
"""
from __future__ import annotations

import os
import sys

import anthropic
from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone

load_dotenv()

# ── Configuration ──────────────────────────────────────────────────────────────
INDEX_NAME   = "redbank-corpus"
EMBED_MODEL  = "text-embedding-3-small"
CLAUDE_MODEL = "claude-sonnet-4-5"
TOP_K        = 5

SYSTEM_PROMPT = (
    "You are a municipal permitting assistant for Red Bank, NJ, built by Navesink Consulting. "
    "RULES: (1) Answer ONLY using the document excerpts provided. Never use general knowledge. "
    "(2) Always cite the source document name and section number for every factual claim. "
    "(3) If the answer is not clearly present in the excerpts, say: I don't have enough information "
    "in my current documents to answer this accurately — please contact the borough directly or "
    "consult a licensed professional. (4) Never provide legal advice. (5) Use plain language."
)

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


def ask_claude(ac: anthropic.Anthropic, question: str, context: str) -> str:
    user_message = (
        f"Here are the relevant document excerpts:\n\n"
        f"{context}\n\n"
        f"Question: {question}"
    )
    msg = ac.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    return msg.content[0].text


# ── Main loop ──────────────────────────────────────────────────────────────────
def main() -> None:
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
    index = pc.Index(INDEX_NAME)

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   Navesink Permitting Assistant — Red Bank, NJ           ║")
    print("║   Powered by Navesink Consulting                         ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print("\nAsk any question about Red Bank permitting, zoning, or")
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

        answer = ask_claude(ac, question, context)

        print("─" * 62)
        print(answer)
        print("─" * 62)
        print()


if __name__ == "__main__":
    main()
