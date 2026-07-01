import React, { useEffect, useState } from 'react';
import { MessageSquareQuote as ChatIcon, X as XIcon, ChevronRight as ArrowIcon } from 'lucide-react';

export interface SupportToastData {
    id: string;
    senderRole: string;
    senderName: string;
    preview: string;
    convoId: string;
    at: number; // Date.now()
}

interface Props {
    toasts: SupportToastData[];
    onDismiss: (id: string) => void;
    onOpen: (convoId: string) => void;
}

const AUTO_DISMISS_MS = 8000;

function relativeTime(ms: number) {
    const s = Math.floor((Date.now() - ms) / 1000);
    if (s < 5) return 'just now';
    if (s < 60) return `${s}s ago`;
    return `${Math.floor(s / 60)}m ago`;
}

const SingleToast: React.FC<{
    toast: SupportToastData;
    onDismiss: (id: string) => void;
    onOpen: (convoId: string) => void;
}> = ({ toast, onDismiss, onOpen }) => {
    const [progress, setProgress] = useState(100);
    const [timeLabel, setTimeLabel] = useState('just now');

    // Shrink the progress bar over AUTO_DISMISS_MS
    useEffect(() => {
        const start = Date.now();
        const tick = setInterval(() => {
            const elapsed = Date.now() - start;
            const pct = Math.max(0, 100 - (elapsed / AUTO_DISMISS_MS) * 100);
            setProgress(pct);
            setTimeLabel(relativeTime(toast.at));
            if (elapsed >= AUTO_DISMISS_MS) {
                clearInterval(tick);
                onDismiss(toast.id);
            }
        }, 100);
        return () => clearInterval(tick);
    }, [toast.id, toast.at, onDismiss]);

    const roleLabel = toast.senderRole.replace(/_/g, ' ');

    return (
        <div
            className="w-80 bg-[#1e1e2e] border border-white/10 rounded-xl shadow-2xl overflow-hidden
                       animate-in slide-in-from-right-4 fade-in duration-300 cursor-pointer group"
            onClick={() => onOpen(toast.convoId)}
            role="button"
            tabIndex={0}
            onKeyDown={e => e.key === 'Enter' && onOpen(toast.convoId)}
        >
            {/* Progress bar — auto-dismiss indicator */}
            <div
                className="h-0.5 bg-teal-500 transition-all duration-100 ease-linear"
                style={{ width: `${progress}%` }}
            />

            <div className="p-3.5">
                <div className="flex items-start gap-3">
                    {/* Icon */}
                    <div className="flex-shrink-0 w-9 h-9 rounded-full bg-teal-600/20 border border-teal-500/30
                                    flex items-center justify-center">
                        <ChatIcon size={16} className="text-teal-400" />
                    </div>

                    <div className="flex-1 min-w-0">
                        {/* Header row */}
                        <div className="flex items-center justify-between mb-0.5">
                            <span className="text-xs font-semibold text-white capitalize truncate">
                                {roleLabel}
                                {toast.senderName && toast.senderName !== roleLabel && (
                                    <span className="text-gray-400 font-normal ml-1">· {toast.senderName}</span>
                                )}
                            </span>
                            <span className="text-[10px] text-gray-500 ml-2 flex-shrink-0">{timeLabel}</span>
                        </div>

                        {/* Sub-header */}
                        <p className="text-[10px] text-teal-400 font-medium uppercase tracking-wide mb-1.5">
                            Support Chat
                        </p>

                        {/* Message preview */}
                        <p className="text-xs text-gray-300 leading-relaxed line-clamp-2">
                            {toast.preview || 'New support message'}
                        </p>
                    </div>

                    {/* Dismiss button */}
                    <button
                        onClick={e => { e.stopPropagation(); onDismiss(toast.id); }}
                        className="flex-shrink-0 p-1 text-gray-600 hover:text-gray-300 rounded transition-colors"
                        title="Dismiss"
                    >
                        <XIcon size={13} />
                    </button>
                </div>

                {/* Open chat CTA */}
                <div className="mt-2.5 flex items-center justify-end">
                    <span className="text-[10px] text-teal-400 group-hover:text-teal-300 flex items-center gap-0.5 transition-colors">
                        Open Support Chat <ArrowIcon size={11} />
                    </span>
                </div>
            </div>
        </div>
    );
};

const SupportChatToast: React.FC<Props> = ({ toasts, onDismiss, onOpen }) => {
    if (toasts.length === 0) return null;

    return (
        <div
            className="fixed bottom-6 right-6 z-[9999] flex flex-col gap-3 items-end pointer-events-none"
            aria-live="polite"
            aria-label="Support chat notifications"
        >
            {toasts.map(t => (
                <div key={t.id} className="pointer-events-auto">
                    <SingleToast toast={t} onDismiss={onDismiss} onOpen={onOpen} />
                </div>
            ))}
        </div>
    );
};

export default SupportChatToast;
