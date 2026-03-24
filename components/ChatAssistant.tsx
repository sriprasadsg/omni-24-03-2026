
import React, { useState, useRef, useEffect } from 'react';
import { ChatMessage } from '../types';
import { getChatAssistantResponse } from '../services/apiService';
// FIX: Replaced non-existent BotMessageSquareIcon with MessageSquareQuoteIcon and added missing SendIcon.
import { XIcon, MessageSquareQuoteIcon, SendIcon, SparklesIcon, UserIcon } from './icons';

interface ChatAssistantProps {
  isOpen: boolean;
  onClose: () => void;
  context: any;
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


export const ChatAssistant: React.FC<ChatAssistantProps> = ({ isOpen, onClose, context }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen) {
      setMessages([{
        role: 'assistant',
        content: `Hello! I'm the Omni-Agent AI. I have context on the current **${context.currentView}** page. Ask me to analyze data, correlate metrics, or even ask business questions like "Did the last deployment impact revenue?"`
      }]);
    }
  }, [isOpen, context.currentView]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage: ChatMessage = { role: 'user', content: input.trim() };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await getChatAssistantResponse(input.trim(), context);
      const assistantMessage: ChatMessage = { role: 'assistant', content: response };
      setMessages(prev => [...prev, assistantMessage]);
    } catch (error) {
      const errorMessage: ChatMessage = {
        role: 'assistant',
        content: `Sorry, I encountered an error. ${error instanceof Error ? error.message : 'Please check the console for details.'}`
      };
      setMessages(prev => [...prev, errorMessage]);
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
        
        <footer className="flex-shrink-0 p-4 border-t border-gray-200 dark:border-gray-700">
          <form onSubmit={handleSendMessage} className="flex items-center space-x-2">
            <input
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              placeholder="Ask about the data on this page..."
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
        </footer>
      </div>
    </div>
  );
};
