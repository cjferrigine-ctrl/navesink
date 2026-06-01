import { NextRequest, NextResponse } from 'next/server';
import OpenAI from 'openai';
import { Pinecone } from '@pinecone-database/pinecone';
import Anthropic from '@anthropic-ai/sdk';
import { TOWNS } from '@/lib/towns';
import type { Citation, Persona } from '@/types';

const CLAUDE_MODEL = 'claude-sonnet-4-6';

const PERSONA_MODIFIERS: Record<Persona, string> = {
  resident:
    'Speak warmly and conversationally, like a knowledgeable neighbor. Use plain language. ' +
    'Open with a brief friendly acknowledgment. Frame next steps encouragingly. ' +
    'Keep all citations and numbers intact.',
  developer:
    'Be direct and technical. Lead with the specific numbers, setbacks, or permit requirements. ' +
    'Use bullet points and checklist format. Skip the preamble. Include all citations. ' +
    'Treat the user as a professional who knows the code.',
  employee:
    'Be citation-first and formal. Quote ordinance language directly where relevant. ' +
    'Include cross-references to related sections. Be efficient and precise. ' +
    'Treat the user as a peer who knows the municipal code.',
};
const TOP_K        = 5;

export async function POST(req: NextRequest) {
  try {
    const { town: townSlug, message, persona } = (await req.json()) as {
      town: string;
      message: string;
      persona?: Persona;
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

    const activePersona: Persona = persona ?? 'resident';
    const systemPrompt = `${town.systemPrompt}\n\n${PERSONA_MODIFIERS[activePersona]}`;

    const claudeResp = await ac.messages.create({
      model: CLAUDE_MODEL,
      max_tokens: 1024,
      system: systemPrompt,
      messages: [{ role: 'user', content: userMessage }],
    });

    const firstBlock = claudeResp.content[0];
    const answer = firstBlock?.type === 'text' ? firstBlock.text : '';

    return NextResponse.json({ answer, citations });
  } catch (err) {
    console.error('[/api/chat]', err);
    return NextResponse.json(
      { error: 'Something went wrong. Please try again.' },
      { status: 500 }
    );
  }
}
