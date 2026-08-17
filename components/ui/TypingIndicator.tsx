import React from 'react';

export const TypingIndicator: React.FC = () => {
  return (
    <div className="flex space-x-1 p-3 bg-slate-700 rounded-lg max-w-[60px]">
      <div className="w-2 h-2 bg-slate-400 rounded-full animate-[typingDot_1.4s_infinite_ease-in-out]" style={{ animationDelay: '0ms' }} />
      <div className="w-2 h-2 bg-slate-400 rounded-full animate-[typingDot_1.4s_infinite_ease-in-out]" style={{ animationDelay: '200ms' }} />
      <div className="w-2 h-2 bg-slate-400 rounded-full animate-[typingDot_1.4s_infinite_ease-in-out]" style={{ animationDelay: '400ms' }} />
    </div>
  );
};