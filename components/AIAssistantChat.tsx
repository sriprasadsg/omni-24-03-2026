import React, { useState, useEffect, useRef } from 'react';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  sources?: any[];
}

export const AIAssistantChat: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const sendMessage = async () => {
    if (!input.trim()) return;
    const userMsg: Message = { role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    // Call API (will implement in apiService.ts)
    // For now, placeholder logic
    const assistantMsg: Message = { role: 'assistant', content: 'Grounded response...' };
    setMessages(prev => [...prev, assistantMsg]);
    setLoading(false);
  };

  return (
    <div className="chat-container">
      <div className="messages" ref={scrollRef}>
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            {msg.content}
            {msg.sources && <div>Sources: {JSON.stringify(msg.sources)}</div>}
          </div>
        ))}
      </div>
      <input value={input} onChange={e => setInput(e.target.value)} />
      <button onClick={sendMessage} disabled={loading}>Send</button>
    </div>
  );
};
