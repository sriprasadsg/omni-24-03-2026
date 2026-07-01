import React from 'react';
import { SparklesIcon } from './icons';

interface ChatFabProps {
  onClick: () => void;
}

export const ChatFab: React.FC<ChatFabProps> = ({ onClick }) => {
  return (
    <button
      onClick={onClick}
      className="fixed bottom-6 right-6 z-40 h-14 w-14 rounded-full bg-primary-600 text-white shadow-lg hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 dark:focus:ring-offset-gray-900 flex items-center justify-center transition-transform hover:scale-110"
      aria-label="Open AI Assistant"
    >
      <SparklesIcon size={28} />
    </button>
  );
};
