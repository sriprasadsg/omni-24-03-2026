import React, { useState } from 'react';
import DOMPurify from 'dompurify';
import { DownloadIcon, CopyIcon, ChevronDownIcon } from './icons';

interface EvidenceMarkdownViewerProps {
    evidence: {
        id: string;
        name: string;
        content?: string;
        details?: string;
    };
}

export const EvidenceMarkdownViewer: React.FC<EvidenceMarkdownViewerProps> = ({ evidence }) => {
    const [isExpanded, setIsExpanded] = useState(false);
    const [copied, setCopied] = useState(false);

    const content = evidence.content || evidence.details || 'No details available.';

    const handleCopy = () => {
        navigator.clipboard.writeText(content);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    const handleDownload = () => {
        const blob = new Blob([content], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${evidence.name.replace(/[^a-z0-9]/gi, '_')}.md`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    // Simple markdown-to-HTML converter for basic formatting
    const renderMarkdown = (md: string) => {
        // Escape all HTML first to prevent XSS — markdown syntax chars are not HTML-special
        const safe = md
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');

        // Replace code blocks (content already HTML-escaped above)
        let html = safe.replace(/```(\w+)?\n([\s\S]*?)```/g, (_, _lang, code) => {
            return `<pre class="bg-gray-900 text-gray-100 dark:bg-gray-950 p-3 rounded-md overflow-x-auto mt-2 mb-2"><code class="text-sm">${code.trim()}</code></pre>`;
        });

        // Replace inline code
        html = html.replace(/`([^`]+)`/g, '<code class="bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-200 px-1.5 py-0.5 rounded text-sm font-mono">$1</code>');

        // Replace headers
        html = html.replace(/^### (.+)$/gm, '<h4 class="text-md font-bold text-gray-900 dark:text-white mt-4 mb-2">$1</h4>');
        html = html.replace(/^## (.+)$/gm, '<h3 class="text-lg font-bold text-gray-900 dark:text-white mt-4 mb-2">$1</h3>');
        html = html.replace(/^# (.+)$/gm, '<h2 class="text-xl font-bold text-gray-900 dark:text-white mt-4 mb-2">$1</h2>');

        // Replace bold
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-gray-900 dark:text-white">$1</strong>');

        // Replace italic
        html = html.replace(/\*(.+?)\*/g, '<em class="italic">$1</em>');

        // Replace line breaks
        html = html.replace(/\n/g, '<br/>');

        return DOMPurify.sanitize(html, {
            ALLOWED_TAGS: ['h2', 'h3', 'h4', 'strong', 'em', 'code', 'pre', 'br', 'li', 'ul', 'ol'],
            ALLOWED_ATTR: ['class'],
            FORBID_ATTR: ['style', 'onerror', 'onload'],
        });
    };

    const escapeHtml = (text: string) => {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    };

    return (
        <div className="border border-gray-200 dark:border-gray-700 rounded-md overflow-hidden">
            <div className="flex items-center justify-between px-3 py-2 bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
                <button
                    onClick={() => setIsExpanded(!isExpanded)}
                    className="flex items-center space-x-2 flex-grow overflow-hidden text-left min-w-0"
                    aria-expanded={isExpanded}
                >
                    {isExpanded ?
                        <ChevronDownIcon size={14} className="text-gray-500 flex-shrink-0" /> :
                        <ChevronDownIcon size={14} className="text-gray-500 flex-shrink-0 -rotate-90" />
                    }
                    <span className="text-xs font-medium text-gray-700 dark:text-gray-300 truncate">
                        {evidence.name}
                    </span>
                </button>
                <div className="flex items-center space-x-2 flex-shrink-0">
                    <button
                        onClick={handleCopy}
                        className="p-1 text-gray-500 hover:text-blue-600 dark:hover:text-blue-400"
                        title={copied ? "Copied!" : "Copy to clipboard"}
                    >
                        <CopyIcon size={12} />
                    </button>
                    <button
                        onClick={handleDownload}
                        className="p-1 text-gray-500 hover:text-green-600 dark:hover:text-green-400"
                        title="Download as .md"
                    >
                        <DownloadIcon size={12} />
                    </button>
                </div>
            </div>

            {isExpanded && (
                <div className="p-4 bg-white dark:bg-gray-900 text-sm text-gray-700 dark:text-gray-300 max-h-96 overflow-y-auto">
                    <div
                        className="prose prose-sm dark:prose-invert max-w-none"
                        dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }}
                    />
                </div>
            )}
        </div>
    );
};
