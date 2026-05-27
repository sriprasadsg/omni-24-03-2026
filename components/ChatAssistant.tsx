
import React, { useState, useRef, useEffect, useCallback } from 'react';
import { ChatMessage } from '../types';
import { getChatAssistantResponse } from '../services/apiService';
import { XIcon, MessageSquareQuoteIcon, SendIcon, SparklesIcon, UserIcon, AlertTriangleIcon } from './icons';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

interface SkillDef {
  name: string;
  description: string;
  usage: string;
  category: string;
}

interface ChatAssistantProps {
  isOpen: boolean;
  onClose: () => void;
  context: any;
  onNavigate?: (view: string) => void;
}

const FormattedMarkdown: React.FC<{ content: string }> = ({ content }) => {
  const parts = content.split(/(`[^`]+`|\*\*.*?\*\*|```[\s\S]*?```)/g);
  return (
    <div className="prose prose-sm dark:prose-invert max-w-none">
      {parts.map((part, index) => {
        if (part.startsWith('**') && part.endsWith('**')) {
          return <strong key={index}>{part.slice(2, -2)}</strong>;
        }
        if (part.startsWith('`') && part.endsWith('`')) {
          return <code key={index} className="bg-gray-200 dark:bg-gray-700 px-1 py-0.5 rounded text-xs">{part.slice(1, -1)}</code>;
        }
        if (part.startsWith('```') && part.endsWith('```')) {
          return <pre key={index} className="bg-gray-900 text-white p-2 rounded-md text-xs whitespace-pre-wrap"><code>{part.slice(3, -3).trim()}</code></pre>;
        }
        return <span key={index}>{part}</span>;
      })}
    </div>
  );
};

export const ChatAssistant: React.FC<ChatAssistantProps> = ({ isOpen, onClose, context, onNavigate }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isMockMode, setIsMockMode] = useState(false);
  const [skills, setSkills] = useState<SkillDef[]>([]);
  const [activeSuggestion, setActiveSuggestion] = useState(0);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    setMessages([{
      role: 'assistant',
      content: `Hello! I'm the Omni-Agent AI. I have context on the current **${context.currentView}** page. Ask me anything, or type \`/\` for a list of quick skills.`
    }]);
    fetch(`${API_BASE}/api/ai`)
      .then(r => r.json())
      .then(d => setIsMockMode(!!d.is_mock_mode))
      .catch(() => {});
    fetch(`${API_BASE}/api/ai/skills`, { credentials: 'include' })
      .then(r => r.ok ? r.json() : [])
      .then((data: SkillDef[]) => setSkills(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, [isOpen, context.currentView]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Reset active suggestion when the query changes
  useEffect(() => {
    setActiveSuggestion(0);
  }, [input]);

  const showSuggestions = input.startsWith('/') && skills.length > 0;
  const query = input.slice(1).toLowerCase();
  const filteredSkills = showSuggestions
    ? skills.filter(s =>
        !query ||
        s.name.startsWith(query) ||
        s.description.toLowerCase().includes(query)
      )
    : [];

  const selectSkill = useCallback((skill: SkillDef) => {
    const hasParams = skill.usage.includes('<');
    setInput(hasParams ? `/${skill.name} ` : `/${skill.name}`);
    setActiveSuggestion(0);
    inputRef.current?.focus();
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!showSuggestions || filteredSkills.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveSuggestion(i => Math.min(i + 1, filteredSkills.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveSuggestion(i => Math.max(i - 1, 0));
    } else if (e.key === 'Tab') {
      e.preventDefault();
      selectSkill(filteredSkills[activeSuggestion]);
    } else if (e.key === 'Escape') {
      setInput('');
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage: ChatMessage = { role: 'user', content: input.trim() };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await getChatAssistantResponse(input.trim(), context);
      setMessages(prev => [...prev, { role: 'assistant', content: response }]);
    } catch (error) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Sorry, I encountered an error. ${error instanceof Error ? error.message : 'Please check the console for details.'}`
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-end items-end" onClick={onClose}>
      <div
        className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-md h-[70vh] m-6 flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        <header className="flex-shrink-0 p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
          <h2 className="text-lg font-bold text-gray-900 dark:text-white flex items-center">
            <MessageSquareQuoteIcon className="mr-3 text-primary-500" />
            Omni-Agent AI Assistant
          </h2>
          <button onClick={onClose} className="p-1 rounded-full text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 focus:outline-none">
            <XIcon size={20} />
          </button>
        </header>

        {isMockMode && (
          <div className="flex-shrink-0 flex items-start gap-2 px-4 py-2 bg-yellow-50 dark:bg-yellow-900/30 border-b border-yellow-200 dark:border-yellow-700/50 text-xs text-yellow-800 dark:text-yellow-300">
            <AlertTriangleIcon size={14} className="mt-0.5 flex-shrink-0" />
            <span>Running in limited mode — no LLM configured. Set <strong>GEMINI_API_KEY</strong> or <strong>OLLAMA_URL</strong>, or{' '}
              {onNavigate ? (
                <button onClick={() => { onNavigate('settings'); onClose(); }} className="underline font-semibold hover:opacity-75">
                  configure LLM provider
                </button>
              ) : (
                <strong>Settings › LLM Provider</strong>
              )}.
            </span>
          </div>
        )}

        <main className="flex-grow p-4 overflow-y-auto space-y-4">
          {messages.map((message, index) => (
            <div key={index} className={`flex items-start gap-3 ${message.role === 'user' ? 'justify-end' : ''}`}>
              {message.role === 'assistant' && (
                <div className="flex-shrink-0 h-8 w-8 rounded-full bg-primary-100 dark:bg-primary-900/50 flex items-center justify-center">
                  <SparklesIcon size={18} className="text-primary-500" />
                </div>
              )}
              <div className={`p-3 rounded-lg max-w-xs ${message.role === 'user' ? 'bg-primary-500 text-white' : 'bg-gray-100 dark:bg-gray-700'}`}>
                <FormattedMarkdown content={message.content} />
              </div>
              {message.role === 'user' && (
                <div className="flex-shrink-0 h-8 w-8 rounded-full bg-gray-200 dark:bg-gray-600 flex items-center justify-center">
                  <UserIcon size={18} />
                </div>
              )}
            </div>
          ))}
          {isLoading && (
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 h-8 w-8 rounded-full bg-primary-100 dark:bg-primary-900/50 flex items-center justify-center">
                <SparklesIcon size={18} className="text-primary-500" />
              </div>
              <div className="p-3 rounded-lg bg-gray-100 dark:bg-gray-700 flex items-center space-x-2">
                <span className="h-2 w-2 bg-primary-500 rounded-full animate-bounce [animation-delay:-0.3s]"></span>
                <span className="h-2 w-2 bg-primary-500 rounded-full animate-bounce [animation-delay:-0.15s]"></span>
                <span className="h-2 w-2 bg-primary-500 rounded-full animate-bounce"></span>
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </main>

        <footer className="flex-shrink-0 border-t border-gray-200 dark:border-gray-700">
          {/* Skill autocomplete dropdown */}
          {showSuggestions && filteredSkills.length > 0 && (
            <div className="border-b border-gray-200 dark:border-gray-700 max-h-48 overflow-y-auto">
              {filteredSkills.map((skill, i) => (
                <button
                  key={skill.name}
                  type="button"
                  onClick={() => selectSkill(skill)}
                  className={`w-full flex items-start gap-3 px-4 py-2 text-left transition-colors ${
                    i === activeSuggestion
                      ? 'bg-primary-50 dark:bg-primary-900/30'
                      : 'hover:bg-gray-50 dark:hover:bg-gray-700/50'
                  }`}
                >
                  <span className="flex-shrink-0 mt-0.5 font-mono text-xs text-primary-600 dark:text-primary-400 w-28 truncate">
                    /{skill.name}
                  </span>
                  <span className="text-xs text-gray-600 dark:text-gray-400 leading-snug">
                    {skill.description}
                  </span>
                </button>
              ))}
              <p className="px-4 py-1.5 text-xs text-gray-400 dark:text-gray-500 border-t border-gray-100 dark:border-gray-700">
                ↑↓ navigate · Tab complete · Enter send
              </p>
            </div>
          )}

          <div className="p-4">
            <form onSubmit={handleSendMessage} className="flex items-center space-x-2">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask a question or type / for skills…"
                disabled={isLoading}
                className="w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-full shadow-sm text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
              <button
                type="submit"
                disabled={isLoading || !input.trim()}
                className="h-9 w-9 flex-shrink-0 rounded-full bg-primary-600 text-white flex items-center justify-center hover:bg-primary-700 disabled:bg-primary-400 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2"
                aria-label="Send message"
              >
                <SendIcon size={18} />
              </button>
            </form>
          </div>
        </footer>
      </div>
    </div>
  );
};
