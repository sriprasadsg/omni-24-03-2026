import React, { useState, useEffect, useRef, useCallback } from 'react';
import { authFetch } from '../services/apiService';
import { showToast } from '../utils/toast';
import { SearchIcon, XIcon, CogIcon, ServerIcon, AlertTriangleIcon, ShieldAlertIcon } from './icons';

interface SearchResult {
    id: string;
    label: string;
    sub: string;
    type: string;
    view: string;
}

interface SearchResponse {
    query: string;
    total: number;
    results: Record<string, SearchResult[]>;
}

const TYPE_META: Record<string, { label: string; icon: React.ReactNode; color: string }> = {
    assets:          { label: 'Assets',          icon: <ServerIcon size={14} />,         color: 'text-blue-500' },
    agents:          { label: 'Agents',           icon: <CogIcon size={14} />,           color: 'text-green-500' },
    alerts:          { label: 'Alerts',           icon: <AlertTriangleIcon size={14} />, color: 'text-amber-500' },
    vulnerabilities: { label: 'Vulnerabilities',  icon: <ShieldAlertIcon size={14} />,   color: 'text-red-500' },
};

interface GlobalSearchModalProps {
    isOpen: boolean;
    onClose: () => void;
    onNavigate: (view: string) => void;
}

export const GlobalSearchModal: React.FC<GlobalSearchModalProps> = ({ isOpen, onClose, onNavigate }) => {
    const [query, setQuery] = useState('');
    const [results, setResults] = useState<SearchResponse | null>(null);
    const [loading, setLoading] = useState(false);
    const [selectedIdx, setSelectedIdx] = useState(0);
    const inputRef = useRef<HTMLInputElement>(null);

    // Reset state when opened
    useEffect(() => {
        if (isOpen) {
            setQuery('');
            setResults(null);
            setSelectedIdx(0);
            setTimeout(() => inputRef.current?.focus(), 80);
        }
    }, [isOpen]);

    // Debounced search
    useEffect(() => {
        if (!query.trim() || query.length < 2) {
            setResults(null);
            return;
        }
        setLoading(true);
        const timer = setTimeout(async () => {
            try {
                const res = await authFetch(`/api/search?q=${encodeURIComponent(query)}`);
                if (res.ok) {
                    const data: SearchResponse = await res.json();
                    setResults(data);
                    setSelectedIdx(0);
                }
            } catch (e) { console.error('Search failed:', e); showToast('Search unavailable — please try again', 'error'); }
            finally { setLoading(false); }
        }, 250);
        return () => clearTimeout(timer);
    }, [query]);

    // Flatten results for keyboard navigation
    const flatItems = results
        ? Object.entries(results.results).flatMap(([, items]) => items)
        : [];

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Escape') { onClose(); return; }
        if (e.key === 'ArrowDown') { e.preventDefault(); setSelectedIdx(i => Math.min(i + 1, flatItems.length - 1)); }
        if (e.key === 'ArrowUp')   { e.preventDefault(); setSelectedIdx(i => Math.max(i - 1, 0)); }
        if (e.key === 'Enter' && flatItems[selectedIdx]) {
            navigateTo(flatItems[selectedIdx]);
        }
    };

    const navigateTo = useCallback((item: SearchResult) => {
        onNavigate(item.view);
        onClose();
    }, [onNavigate, onClose]);

    if (!isOpen) return null;

    const hasResults = results && results.total > 0;
    let globalIdx = 0;

    return (
        <div className="fixed inset-0 bg-black/60 z-[60] flex items-start justify-center pt-[15vh]" onClick={onClose}>
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-2xl border border-gray-200 dark:border-gray-700 overflow-hidden"
                 onClick={e => e.stopPropagation()}>

                {/* Search input */}
                <div className="flex items-center px-4 py-3 border-b border-gray-200 dark:border-gray-700">
                    {loading
                        ? <CogIcon size={18} className="text-gray-400 mr-3 animate-spin flex-shrink-0" />
                        : <SearchIcon size={18} className="text-gray-400 mr-3 flex-shrink-0" />}
                    <input
                        ref={inputRef}
                        type="text"
                        value={query}
                        onChange={e => setQuery(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="Search assets, agents, alerts, CVEs…"
                        className="flex-1 text-sm bg-transparent text-gray-900 dark:text-gray-100 placeholder-gray-400 outline-none"
                    />
                    {query && (
                        <button onClick={() => { setQuery(''); setResults(null); inputRef.current?.focus(); }}
                            className="ml-2 p-1 rounded text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
                            <XIcon size={15} />
                        </button>
                    )}
                    <kbd className="ml-3 px-1.5 py-0.5 text-xs border border-gray-300 dark:border-gray-600 rounded text-gray-400 font-mono">Esc</kbd>
                </div>

                {/* Results */}
                <div className="max-h-[420px] overflow-y-auto">
                    {!query.trim() && (
                        <div className="px-4 py-8 text-center text-sm text-gray-400 dark:text-gray-500">
                            Type to search across assets, agents, alerts, and vulnerabilities
                        </div>
                    )}

                    {query.trim().length >= 2 && !loading && results?.total === 0 && (
                        <div className="px-4 py-8 text-center text-sm text-gray-400 dark:text-gray-500">
                            No results for <span className="font-medium text-gray-600 dark:text-gray-300">"{query}"</span>
                        </div>
                    )}

                    {hasResults && Object.entries(results!.results).map(([type, items]) => {
                        if (items.length === 0) return null;
                        const meta = TYPE_META[type] || { label: type, icon: <SearchIcon size={14} />, color: 'text-gray-500' };
                        return (
                            <div key={type}>
                                {/* Category header */}
                                <div className="px-4 py-2 flex items-center gap-2 bg-gray-50 dark:bg-gray-700/50 sticky top-0">
                                    <span className={meta.color}>{meta.icon}</span>
                                    <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                        {meta.label} ({items.length})
                                    </span>
                                </div>
                                {/* Items */}
                                {items.map(item => {
                                    const myIdx = globalIdx++;
                                    const isSelected = myIdx === selectedIdx;
                                    return (
                                        <button key={item.id || item.label}
                                            onClick={() => navigateTo(item)}
                                            onMouseEnter={() => setSelectedIdx(myIdx)}
                                            className={`w-full flex items-start gap-3 px-4 py-3 text-left transition-colors ${isSelected ? 'bg-primary-50 dark:bg-primary-900/30' : 'hover:bg-gray-50 dark:hover:bg-gray-700/40'}`}>
                                            <span className={`mt-0.5 flex-shrink-0 ${meta.color}`}>{meta.icon}</span>
                                            <div className="min-w-0">
                                                <p className={`text-sm font-medium truncate ${isSelected ? 'text-primary-700 dark:text-primary-300' : 'text-gray-900 dark:text-gray-100'}`}>
                                                    {item.label}
                                                </p>
                                                <p className="text-xs text-gray-500 dark:text-gray-400 truncate mt-0.5">{item.sub}</p>
                                            </div>
                                            <span className="ml-auto flex-shrink-0 text-xs text-gray-300 dark:text-gray-600 self-center">↵</span>
                                        </button>
                                    );
                                })}
                            </div>
                        );
                    })}
                </div>

                {/* Footer */}
                {hasResults && (
                    <div className="px-4 py-2 border-t border-gray-100 dark:border-gray-700 flex items-center gap-4 text-xs text-gray-400 dark:text-gray-500">
                        <span>{results!.total} result{results!.total !== 1 ? 's' : ''}</span>
                        <span className="flex items-center gap-1"><kbd className="px-1 py-0.5 border border-gray-300 dark:border-gray-600 rounded font-mono">↑↓</kbd> navigate</span>
                        <span className="flex items-center gap-1"><kbd className="px-1 py-0.5 border border-gray-300 dark:border-gray-600 rounded font-mono">↵</kbd> open</span>
                    </div>
                )}
            </div>
        </div>
    );
};
