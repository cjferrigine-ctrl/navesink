import { NextRequest, NextResponse } from 'next/server';
import OpenAI from 'openai';
import { Pinecone } from '@pinecone-database/pinecone';
import Anthropic from '@anthropic-ai/sdk';
import { TOWNS } from '@/lib/towns';
import type { Citation } from '@/types';

const CLAUDE_MODEL = 'claude-sonnet-4-5';
const TOP_K        = 5;

export async function POST(req: NextRequest) {
  try {
    const { town: townSlug, message } = (await req.json()) as {
      town: string;
      message: string;
    };

    const town = TOWNS[townSlug];
    if (!town) {
      return NextResponse.json({ error: 'Unknown town.' }, { status: 400 });
    }
    if (!message?.trim()) {
      return NextResponse.json({ error: 'Message is required.' }, { status: 400 });
    }

    const oai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY! });
    const pc  = new Pinecone({ apiKey: process.env.PINECONE_API_KEY! });
    const ac  = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY! });

    // 1 — Embed the question
    const embResp = await oai.embeddings.create({
      model: 'text-embedding-3-small',
      input: message.trim(),
    });
    const vector = embResp.data[0].embedding;

    // 2 — Query Pinecone
    const index   = pc.index(town.pineconeIndex);
    const results = await index.query({ vector, topK: TOP_K, includeMetadata: true });

    // 3 — Build context string and citation objects
    const citations: Citation[] = [];
    const contextParts: string[] = [];

    results.matches.forEach((match, i) => {
      const meta    = match.metadata ?? {};
      const source  = String(meta.source          ?? 'Unknown');
      const page    = Number(meta.page            ?? 0);
      const section = String(meta.section_header  ?? '');
      const docType = String(meta.doc_type        ?? 'other');
      const text    = String(meta.text            ?? '');

      citations.push({ source, page, section, docType, excerpt: text.slice(0, 400) });

      let header = `[Excerpt ${i + 1}]  Source: ${source}`;
      if (page)    header += `  |  Page: ${page}`;
      if (section) header += `  |  Section: ${section}`;
      contextParts.push(`${header}\n${text}`);
    });

    const context = contextParts.join('\n\n---\n\n');

    // 4 — Call Claude
    const userMessage =
      `Here are the relevant document excerpts:\n\n${context}\n\nQuestion: ${message.trim()}`;

    const claudeResp = await ac.messages.create({
      model: CLAUDE_MODEL,
      max_tokens: 1024,
      system: town.systemPrompt,
      messages: [{ role: 'user', content: userMessage }],
    });

    const answer =
      claudeResp.content[0].type === 'text' ? claudeResp.content[0].text : '';

    return NextResponse.json({ answer, citations });
  } catch (err) {
    console.error('[/api/chat]', err);
    return NextResponse.json(
      { error: 'Something went wrong. Please try again.' },
      { status: 500 }
    );
  }
}
