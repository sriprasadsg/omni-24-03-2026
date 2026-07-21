import React, { useState, useEffect } from 'react';
import { MessageSquareIcon, SendIcon, ClockIcon } from './icons';
import * as api from '../services/apiService';
import { showToast } from '../utils/toast';
import { useUser } from '../contexts/UserContext';

interface ControlCommentsPanelProps {
    controlId: string;
}

// Kept in sync by hand with backend/control_comments_endpoints.py's
// _COMMENT_AUTHOR_ROLES. Backend always re-enforces authorization
// server-side regardless of this list, so drift here is a UI-confusion
// risk (composer visibility), not an authz bypass.
const _REVIEWER_ROLES = ['admin', 'super_admin', 'compliance_reviewer'];

function formatTimestamp(ts: string): string {
    try {
        return new Date(ts).toLocaleString('en-US', {
            timeZone: 'UTC',
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    } catch {
        return ts;
    }
}

// NEVER use the raw-HTML injection prop. Split on mention tokens and wrap
// in a span; all text still flows through React's default JSX child escaping.
function renderCommentText(text: string) {
    const parts = text.split(/(@[\w.-]+)/g);
    return parts.map((part, i) =>
        /^@[\w.-]+$/.test(part)
            ? <span key={i} className="text-blue-600 dark:text-blue-400 font-medium">{part}</span>
            : <React.Fragment key={i}>{part}</React.Fragment>
    );
}

export const ControlCommentsPanel: React.FC<ControlCommentsPanelProps> = ({ controlId }) => {
    const { currentUser } = useUser();
    const [comments, setComments] = useState<any[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [text, setText] = useState('');
    const [submitting, setSubmitting] = useState(false);
    const [postError, setPostError] = useState<string | null>(null);

    const isReviewer = currentUser && _REVIEWER_ROLES.includes(currentUser.role);

    useEffect(() => {
        let cancelled = false;
        (async () => {
            setLoading(true);
            setError(null);
            try {
                const data = await api.fetchControlComments(controlId);
                if (!cancelled) setComments(data);
            } catch {
                if (!cancelled) setError('Failed to load comments. Retry by collapsing and expanding this panel.');
            } finally {
                if (!cancelled) setLoading(false);
            }
        })();
        return () => { cancelled = true; };
    }, [controlId]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        const trimmed = text.trim();
        if (!trimmed) return;
        setSubmitting(true);
        setPostError(null);
        try {
            const comment = await api.postControlComment(controlId, trimmed);
            setComments(prev => [...prev, comment]);
            setText('');
            showToast('Comment posted.', 'success');
        } catch {
            setPostError('Failed to post comment — please try again.');
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div className="mt-4">
            <div className="flex items-center justify-between px-4 py-2 bg-gray-100 dark:bg-gray-700/50 rounded-t-md border border-gray-200 dark:border-gray-700">
                <span className="text-sm font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-1.5">
                    <MessageSquareIcon size={14} />
                    Comments
                    <span className="text-xs font-normal text-gray-400">({comments.length})</span>
                </span>
            </div>

            <div className="border border-t-0 border-gray-200 dark:border-gray-700 rounded-b-md bg-white dark:bg-gray-800">
                {loading && (
                    <div className="flex justify-center py-4">
                        <svg className="animate-spin h-4 w-4 text-gray-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                        </svg>
                    </div>
                )}
                {!loading && error && (
                    <p className="px-4 py-4 text-xs text-red-500">
                        {error}
                    </p>
                )}
                {!loading && !error && comments.length === 0 && (
                    <p className="px-4 py-6 text-center text-xs text-gray-400 italic">
                        No comments yet on this control.
                    </p>
                )}
                {!loading && !error && comments.length > 0 && (
                    <div className="divide-y divide-gray-100 dark:divide-gray-700/50">
                        {comments.map((c, idx) => {
                            const author = c.author ?? 'unknown';
                            const ts = c.created_at ?? '';
                            const commentKey = c.id ?? `comment-${idx}`;
                            return (
                                <div key={commentKey} className="px-4 py-3">
                                    <div className="flex items-start gap-2">
                                        <div className="flex-shrink-0 mt-0.5">
                                            <ClockIcon size={14} className="text-gray-400" />
                                        </div>
                                        <div className="min-w-0">
                                            <p className="text-xs font-semibold text-gray-800 dark:text-gray-200">
                                                {author} <span className="font-normal text-gray-500">{formatTimestamp(ts)} UTC</span>
                                            </p>
                                            <p className="text-xs text-gray-600 dark:text-gray-400 mt-0.5 whitespace-pre-wrap break-words">
                                                {renderCommentText(c.text ?? '')}
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}

                {isReviewer && (
                    <form onSubmit={handleSubmit} className="px-4 py-3 border-t border-gray-200 dark:border-gray-700">
                        <textarea
                            className="w-full text-xs p-2 border rounded dark:bg-gray-700 dark:border-gray-600"
                            rows={2}
                            placeholder="Add a comment... (use @username to mention someone)"
                            value={text}
                            onChange={e => setText(e.target.value)}
                        />
                        {postError && (
                            <p className="text-xs text-red-500 mt-1">{postError}</p>
                        )}
                        <div className="flex justify-end mt-2">
                            <button
                                type="submit"
                                disabled={submitting || !text.trim()}
                                className="flex items-center gap-1 text-xs px-3 py-2 rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50"
                            >
                                <SendIcon size={14} aria-hidden="true" />
                                {submitting ? 'Posting...' : 'Post Comment'}
                            </button>
                        </div>
                    </form>
                )}
            </div>
        </div>
    );
};
