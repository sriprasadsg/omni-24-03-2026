import React from 'react';
import { AiSystem, AiSystemDocumentationLink } from '../types';
import { FileCodeIcon, ExternalLinkIcon, BookTextIcon, ClipboardCheckIcon } from './icons';

interface AiSystemDocumentationProps {
  system: AiSystem;
}

const docTypeIcons: Record<AiSystemDocumentationLink['type'], React.ReactNode> = {
    'Model Card': <BookTextIcon size={16} className="text-blue-500" />,
    'Technical Paper': <ClipboardCheckIcon size={16} className="text-green-500" />,
    'API Reference': <FileCodeIcon size={16} className="text-purple-500" />,
    'Other': <FileCodeIcon size={16} className="text-gray-500" />,
};

export const AiSystemDocumentation: React.FC<AiSystemDocumentationProps> = ({ system }) => {
  const { documentation } = system;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-semibold flex items-center">
          <FileCodeIcon className="mr-2 text-primary-500" />
          AI System Documentation
        </h3>
      </div>
      <div className="p-4">
        {documentation && documentation.length > 0 ? (
          <div className="space-y-3">
            {documentation.map(doc => (
              <a
                key={doc.id}
                href={doc.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-between p-3 rounded-lg bg-gray-50 dark:bg-gray-700/50 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              >
                <div className="flex items-center">
                    {docTypeIcons[doc.type]}
                    <span className="ml-3 font-medium text-gray-700 dark:text-gray-300">{doc.title}</span>
                </div>
                <ExternalLinkIcon size={14} className="text-gray-400 dark:text-gray-500" />
              </a>
            ))}
          </div>
        ) : (
          <p className="text-sm text-center text-gray-500 dark:text-gray-400 py-4">
            No documentation has been linked for this system.
          </p>
        )}
      </div>
    </div>
  );
};
