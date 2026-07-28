import React, { Suspense, lazy, useState } from 'react';
import { MessageSquare, Minus, X as XIcon, Maximize2 } from 'lucide-react';

const SupportChatPanel = lazy(() => import('./SupportChatPanel'));

interface SupportChatWindowProps {
    isOpen: boolean;
    /** Conversation to auto-open (deep-link from a toast / notification). */
    initialConvoId?: string | null;
    /** Fired once the deep-linked conversation has been opened. */
    onConvoConsumed?: () => void;
    onClose: () => void;
}

/**
 * Floating, docked support-chat window. Overlays the current page (bottom-right)
 * so the user can chat with support inline instead of being navigated to a
 * full-page view. Hosts the shared SupportChatPanel so all conversation logic,
 * polling and presence are reused unchanged.
 */
const SupportChatWindow: React.FC<SupportChatWindowProps> = ({
    isOpen,
    initialConvoId = null,
    onConvoConsumed,
    onClose,
}) => {
    const [minimized, setMinimized] = useState(false);

    if (!isOpen) return null;

    return (
        <div
            className="fixed bottom-6 right-6 z-[9998] flex flex-col
                       w-[min(780px,calc(100vw-3rem))]
                       bg-slate-950 border border-white/10 rounded-xl shadow-2xl
                       overflow-hidden animate-in slide-in-from-bottom-4 fade-in duration-300"
            style={{ height: minimized ? 'auto' : 'min(620px, calc(100vh - 6rem))' }}
            role="dialog"
            aria-label="Support chat"
        >
            {/* ── Title bar ─────────────────────────────────────────────── */}
            <div className="flex items-center justify-between gap-3 px-4 py-2.5
                            border-b border-slate-800 bg-slate-900/80 flex-shrink-0">
                <div className="flex items-center gap-2 min-w-0">
                    <div className="w-7 h-7 rounded-full bg-teal-600/20 border border-teal-500/30
                                    flex items-center justify-center flex-shrink-0">
                        <MessageSquare size={14} className="text-teal-400" />
                    </div>
                    <span className="text-sm font-semibold text-white truncate">Support Chat</span>
                </div>
                <div className="flex items-center gap-1 flex-shrink-0">
                    <button
                        onClick={() => setMinimized(m => !m)}
                        className="p-1.5 text-gray-400 hover:text-white hover:bg-white/5 rounded transition-colors"
                        title={minimized ? 'Expand' : 'Minimize'}
                        aria-label={minimized ? 'Expand' : 'Minimize'}
                    >
                        {minimized ? <Maximize2 size={14} /> : <Minus size={14} />}
                    </button>
                    <button
                        onClick={onClose}
                        className="p-1.5 text-gray-400 hover:text-white hover:bg-white/5 rounded transition-colors"
                        title="Close"
                        aria-label="Close support chat"
                    >
                        <XIcon size={15} />
                    </button>
                </div>
            </div>

            {/* ── Body: shared support panel ────────────────────────────── */}
            {!minimized && (
                <div className="flex-1 min-h-0 overflow-hidden">
                    <Suspense
                        fallback={
                            <div className="flex-1 h-full flex items-center justify-center text-slate-500 text-sm">
                                Loading…
                            </div>
                        }
                    >
                        <SupportChatPanel
                            initialConvoId={initialConvoId}
                            onConvoConsumed={onConvoConsumed}
                        />
                    </Suspense>
                </div>
            )}
        </div>
    );
};

export default SupportChatWindow;
