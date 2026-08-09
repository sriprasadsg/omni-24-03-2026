import React, { useState, useRef, useEffect } from 'react';
import { chatWithAssistant } from '../services/apiService';

import { TypingIndicator } from './ui/TypingIndicator';
import { ContextCard } from './ui/ContextCard';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  sources?: any[];
  isStreaming?: boolean;
}

const StreamingText: React.FC<{ text: string; isStreaming: boolean }> = ({ text, isStreaming }) => {
  const [displayedText, setDisplayedText] = useState('');
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    setPrefersReducedMotion(mediaQuery.matches);
    const handler = (event: MediaQueryListEvent) => setPrefersReducedMotion(event.matches);
    mediaQuery.addEventListener('change', handler);
    return () => mediaQuery.removeEventListener('change', handler);
  }, []);

  useEffect(() => {
    if (!isStreaming || prefersReducedMotion) {
      setDisplayedText(text);
      return;
    }

    let i = 0;
    const intervalId = setInterval(() => {
      setDisplayedText(text.slice(0, i));
      i++;
      if (i > text.length) {
        clearInterval(intervalId);
      }
    }, 15); // Adjust typing speed here

    return () => clearInterval(intervalId);
  }, [text, isStreaming, prefersReducedMotion]);

  return (
    <>
      {displayedText}
      {isStreaming && <span className="ml-0.5 animate-pulse">▎</span>}
    </>
  );
};

export const AIAssistantChat: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const cancelRef = useRef<(() => void) | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, streamingContent]);

  const sendMessage = async () => {
    const q = input.trim();
    if (!q || loading) return;

    const userMsg: Message = { role: 'user', content: q };
    const history = [...messages, userMsg];
    setMessages(history);
    setInput('');
    setLoading(true);
    setStreamingContent('');

    // Append empty assistant bubble to fill in via streaming
    setMessages(prev => [...prev, { role: 'assistant', content: '', sources: [], isStreaming: true }]);

    cancelRef.current = chatWithAssistant(
      q,
      history.slice(0, -1),
      chunk => {
        setStreamingContent(prev => prev + chunk);
      },
      sources => {
        setMessages(prev => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last && last.role === 'assistant') {
            next[next.length - 1] = {
              role: 'assistant',
              content: (last.content || '') + (streamingContent || ''),
              sources,
              isStreaming: false,
            };
          }
          return next;
        });
        setStreamingContent('');
        setLoading(false);
      },
      err => {
        setMessages(prev => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last && last.role === 'assistant') {
            next[next.length - 1] = { role: 'assistant', content: `Error: ${err}`, isStreaming: false };
          }
          return next;
        });
        setStreamingContent('');
        setLoading(false);
      }
    );
  };

  const cancel = () => {
    cancelRef.current?.();
    cancelRef.current = null;
    setLoading(false);
  };

  return (
    <div className="flex flex-col h-full bg-slate-900 text-slate-100">
      <div className="flex-1 overflow-y-auto p-4 space-y-3" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="text-slate-400 text-center mt-10">
            Ask a question about your compliance or security posture.
          </div>
        )}
        {messages.map((msg, i) => {
          const streamed = loading && i === messages.length - 1 && msg.role === 'assistant';
          const displayContent = msg.role === 'assistant' ? msg.content : msg.content;
          const isStructured = msg.sources && msg.sources.some(s => s.metadata?.type);
          return (
            <div
              key={i}
              className={`max-w-3xl rounded-lg p-3 ${msg.role === 'user' ? 'ml-auto bg-blue-600' : 'mr-auto bg-slate-700'}`}
            >
              {isStructured && msg.role === 'assistant' ? (
                <ContextCard
                  type="finding"
                  title="AI Analysis"
                  description={displayContent}
                  metadata={{ sources: msg.sources?.length, timestamp: new Date().toISOString() }}
                />
              ) : (
                <div className="whitespace-pre-wrap">
                  {msg.role === 'assistant' ? (
                    streamed && !displayContent ? <TypingIndicator /> : <StreamingText text={displayContent} isStreaming={streamed} />
                  ) : (
                    displayContent
                  )}
                </div>
              )}
              {!isStructured && msg.sources && msg.sources.length > 0 && (
                <div className="mt-2 pt-2 border-t border-slate-600 text-xs">
                  <div className="font-semibold text-slate-300">Sources:</div>
                  {msg.sources.map((s, j) => (
                    <div key={j} className="text-slate-400">
                      [{s.type}] {s.title} — <span className="italic">{s.snippet}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div className="p-3 border-t border-slate-700 flex gap-2">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              sendMessage();
            }
          }}
          placeholder="Ask about your compliance posture..."
          disabled={loading}
          className="flex-1 bg-slate-800 border border-slate-700 rounded px-3 py-2 text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500"
        />
        {loading ? (
          <button onClick={cancel} className="bg-red-600 hover:bg-red-700 px-4 py-2 rounded">
            Cancel
          </button>
        ) : (
          <button onClick={sendMessage} disabled={!input.trim()} className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded disabled:opacity-50">
            Send
          </button>
        )}
      </div>
    </div>
  );
};
