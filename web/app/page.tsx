'use client';

import { useState, useRef, useEffect } from 'react';
import { TOWNS, DEFAULT_TOWN } from '@/lib/towns';
import type { Message, Persona } from '@/types';

const PERSONA_OPTIONS: { value: Persona; label: string; icon: string }[] = [
  { value: 'resident',  label: "I'm a Resident",        icon: '🏠' },
  { value: 'developer', label: 'Developer / Contractor', icon: '🔨' },
  { value: 'employee',  label: 'Borough Employee',       icon: '🏛️' },
];

const PERSONA_DISPLAY: Record<Persona, { label: string; icon: string }> = {
  resident:  { label: 'Resident',             icon: '🏠' },
  developer: { label: 'Developer/Contractor', icon: '🔨' },
  employee:  { label: 'Borough Employee',     icon: '🏛️' },
};

export default function HomePage() {
  const [townSlug, setTownSlug]   = useState(DEFAULT_TOWN);
  const [messages, setMessages]   = useState<Message[]>([]);
  const [input, setInput]         = useState('');
  const [loading, setLoading]     = useState(false);
  const [expanded, setExpanded]   = useState<Set<string>>(new Set());
  const [persona, setPersona]     = useState<Persona | null>(null);
  const bottomRef                 = useRef<HTMLDivElement>(null);
  const textareaRef               = useRef<HTMLTextAreaElement>(null);

  const town = TOWNS[townSlug];

  // Clear chat and persona when town changes
  useEffect(() => {
    setMessages([]);
    setExpanded(new Set());
    setPersona(null);
  }, [townSlug]);

  const handleChangePersona = () => {
    setPersona(null);
    setMessages([]);
    setExpanded(new Set());
  };

  // Auto-scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px';
  };

  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: Message = { id: `u-${Date.now()}`, role: 'user', content: text };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    setLoading(true);

    try {
      const res  = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ town: townSlug, message: text, persona: persona ?? 'resident' }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Request failed');

      setMessages(prev => [
        ...prev,
        { id: `a-${Date.now()}`, role: 'assistant', content: data.answer, citations: data.citations },
      ]);
    } catch {
      setMessages(prev => [
        ...prev,
        { id: `e-${Date.now()}`, role: 'assistant', content: 'Something went wrong. Please try again.' },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const toggleExpanded = (id: string) =>
    setExpanded(prev => {
      const s = new Set(prev);
      s.has(id) ? s.delete(id) : s.add(id);
      return s;
    });

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* Header */}
      <header
        className="shrink-0 flex items-center justify-between px-6 py-3 shadow-md"
        style={{ backgroundColor: '#1a2e4a' }}
      >
        <div className="flex items-baseline gap-3">
          <span className="text-white font-bold text-lg tracking-tight">Navesink</span>
          <span className="text-blue-300 text-sm hidden sm:inline">Municipal Permitting Assistant</span>
        </div>
        <div className="flex items-center gap-3">
          {persona && (
            <div className="flex items-center gap-1.5 bg-blue-800 rounded-full px-3 py-1 text-xs text-blue-100">
              <span>{PERSONA_DISPLAY[persona].icon}</span>
              <span>{PERSONA_DISPLAY[persona].label}</span>
              <button
                onClick={handleChangePersona}
                className="ml-1 text-blue-300 hover:text-white transition-colors underline underline-offset-2"
              >
                Change
              </button>
            </div>
          )}
          <div className="flex items-center gap-2">
            <span className="text-blue-300 text-sm">Town:</span>
            <select
              value={townSlug}
              onChange={e => setTownSlug(e.target.value)}
              className="rounded-lg bg-white text-gray-900 px-3 py-1.5 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-blue-400 cursor-pointer"
            >
              {Object.values(TOWNS).map(t => (
                <option key={t.slug} value={t.slug}>
                  {t.name}, {t.state}
                </option>
              ))}
            </select>
          </div>
        </div>
      </header>

      {/* Chat messages */}
      <main className="flex-1 overflow-y-auto bg-gray-50 px-4 py-6">
        <div className="max-w-2xl mx-auto">
          {messages.length === 0 ? (
            <div className="text-center mt-16 px-4">
              <div className="text-5xl mb-4">🏛️</div>
              <h2 className="text-xl font-semibold text-gray-700 mb-2">
                {town.name} Permitting Assistant
              </h2>
              {!persona ? (
                <div className="mt-6 max-w-sm mx-auto">
                  <p className="text-gray-600 text-sm mb-4 leading-relaxed">
                    Before we get started — who are you? This helps me tailor my answers.
                  </p>
                  <div className="flex flex-col gap-2">
                    {PERSONA_OPTIONS.map(opt => (
                      <button
                        key={opt.value}
                        onClick={() => setPersona(opt.value)}
                        className="flex items-center gap-3 w-full rounded-xl border border-gray-200 bg-white
                                   px-4 py-3 text-sm font-medium text-gray-700 shadow-sm
                                   hover:border-blue-400 hover:bg-blue-50 hover:text-blue-700
                                   transition-colors text-left"
                      >
                        <span className="text-lg">{opt.icon}</span>
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="text-gray-500 text-sm max-w-sm mx-auto leading-relaxed">
                  Ask about zoning, setbacks, permitted uses, historic preservation,
                  fees, or any other {town.name} permitting topic.
                </p>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              {messages.map(msg => (
                <div
                  key={msg.id}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[82%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                      msg.role === 'user'
                        ? 'bg-blue-600 text-white rounded-br-sm'
                        : 'bg-white text-gray-800 shadow-sm border border-gray-200 rounded-bl-sm'
                    }`}
                  >
                    <p className="whitespace-pre-wrap">{msg.content}</p>

                    {/* Citations */}
                    {msg.citations && msg.citations.length > 0 && (
                      <div className="mt-3 pt-3 border-t border-gray-100">
                        <button
                          onClick={() => toggleExpanded(msg.id)}
                          className="flex items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-700 transition-colors"
                        >
                          <span>📄</span>
                          <span>
                            {msg.citations.length} source{msg.citations.length !== 1 ? 's' : ''}
                          </span>
                          <span>{expanded.has(msg.id) ? '▲' : '▼'}</span>
                        </button>

                        {expanded.has(msg.id) && (
                          <div className="mt-2 space-y-2">
                            {msg.citations.map((c, i) => (
                              <div
                                key={i}
                                className="bg-gray-50 border border-gray-100 rounded-lg p-3 text-xs"
                              >
                                <div className="font-medium text-gray-700 mb-1">
                                  {c.source}
                                  {c.page ? ` · p. ${c.page}` : ''}
                                  {c.section ? ` · ${c.section}` : ''}
                                </div>
                                {c.excerpt && (
                                  <p className="text-gray-500 italic leading-relaxed">
                                    &ldquo;{c.excerpt.slice(0, 220)}&hellip;&rdquo;
                                  </p>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {/* Typing indicator */}
              {loading && (
                <div className="flex justify-start">
                  <div className="bg-white rounded-2xl rounded-bl-sm shadow-sm border border-gray-200 px-4 py-3">
                    <div className="flex gap-1.5 items-center h-4">
                      {[0, 150, 300].map(delay => (
                        <div
                          key={delay}
                          className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                          style={{ animationDelay: `${delay}ms` }}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              )}

              <div ref={bottomRef} className="h-2" />
            </div>
          )}
        </div>
      </main>

      {/* Input bar */}
      <footer className="shrink-0 bg-white border-t border-gray-200 px-4 py-3">
        <div className="max-w-2xl mx-auto">
          <div className="flex gap-3 items-end">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleTextareaChange}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              placeholder={`Ask about ${town.name} permitting…`}
              rows={1}
              disabled={loading}
              className="flex-1 resize-none rounded-xl border border-gray-300 px-4 py-2.5 text-sm
                         focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
                         disabled:bg-gray-50 disabled:text-gray-400"
              style={{ minHeight: '44px', maxHeight: '120px', overflowY: 'auto' }}
            />
            <button
              onClick={send}
              disabled={!input.trim() || loading}
              className="shrink-0 bg-blue-600 text-white px-5 py-2.5 rounded-xl text-sm font-medium
                         hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Send
            </button>
          </div>
          <p className="text-center text-xs text-gray-400 mt-2">
            Powered by Navesink Consulting &nbsp;·&nbsp; Not legal advice &nbsp;·&nbsp; Enter to send, Shift+Enter for new line
          </p>
        </div>
      </footer>
    </div>
  );
}
