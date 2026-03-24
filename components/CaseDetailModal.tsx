
import React, { useState, useRef, useEffect, useMemo } from 'react';
import { SecurityCase, Comment, ThreatIntelResult, User } from '../types';
import { useUser } from '../contexts/UserContext';
import { useTimeZone } from '../contexts/TimeZoneContext';
import { XIcon, UserIcon, ClockIcon, MessageSquareQuoteIcon, PaperclipIcon, ExternalLinkIcon, ShieldSearchIcon, CheckIcon, AlertTriangleIcon, Share2Icon } from './icons';

interface CaseDetailModalProps {
    isOpen: boolean;
    onClose: () => void;
    caseItem: SecurityCase | null;
    onAddComment: (caseId: string, content: string) => void;
    users: User[];
    onAnalyzeImpact: (type: 'case', id: string) => void;
}

const IntelResultCard: React.FC<{ result: ThreatIntelResult }> = ({ result }) => {
    const isMalicious = result.verdict === 'Malicious' || result.verdict === 'Suspicious';
    return (
        <div className={`p-3 rounded-lg border ${isMalicious ? 'bg-red-50 dark:bg-red-900/50 border-red-200 dark:border-red-800' : 'bg-gray-50 dark:bg-gray-700/50 border-gray-200 dark:border-gray-600'}`}>
            <div className="flex justify-between items-start">
                <div>
                    <p className="font-semibold text-gray-800 dark:text-gray-200 font-mono text-xs">{result.artifact}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">Scanned via {result.source}</p>
                </div>
                <div className="text-right">
                    <p className={`font-bold text-sm ${isMalicious ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'}`}>{result.verdict}</p>
                    <p className={`text-xs font-semibold ${isMalicious ? 'text-red-500' : 'text-gray-500 dark:text-gray-400'}`}>{result.detectionRatio} detections</p>
                </div>
            </div>
            <a href={result.reportUrl} target="_blank" rel="noopener noreferrer" className="mt-2 text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline flex items-center">
                View Full Report <ExternalLinkIcon size={12} className="ml-1.5" />
            </a>
        </div>
    );
};

export const CaseDetailModal: React.FC<CaseDetailModalProps> = ({ isOpen, onClose, caseItem, onAddComment, users, onAnalyzeImpact }) => {
    const { currentUser, hasPermission } = useUser();
    const canManageCases = hasPermission('manage:security_cases');
    const canInvestigate = hasPermission('investigate:security');
    const { timeZone } = useTimeZone();
    const [newComment, setNewComment] = useState('');
    const commentsEndRef = useRef<HTMLDivElement>(null);

    const userAvatarMap = useMemo(() => {
        return users.reduce((acc, user) => {
            acc[user.name] = user.avatar;
            return acc;
        }, {} as Record<string, string>);
    }, [users]);

    const findUserAvatar = (userName: string) => {
        return userAvatarMap[userName] || 'https://i.pravatar.cc/150';
    };

    useEffect(() => {
        commentsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [caseItem?.comments, isOpen]);

    const handleSubmitComment = (e: React.FormEvent) => {
        e.preventDefault();
        if (newComment.trim() && caseItem) {
            onAddComment(caseItem.id, newComment.trim());
            setNewComment('');
        }
    };

    if (!isOpen || !caseItem) return null;

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl p-6 m-4 max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
                <div className="flex-shrink-0 flex justify-between items-start mb-4">
                    <div>
                        <h2 className="text-xl font-bold text-gray-900 dark:text-white">{caseItem.title}</h2>
                        <p className="text-sm text-gray-500 dark:text-gray-400">{caseItem.id}</p>
                    </div>
                    <button onClick={onClose} className="p-1 rounded-full text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 focus:outline-none">
                        <XIcon size={20} />
                    </button>
                </div>

                <div className="flex-grow space-y-4 overflow-y-auto pr-2">
                    {/* Case Details */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
                        <div><strong className="block text-gray-500 dark:text-gray-400">Status</strong> {caseItem.status}</div>
                        <div><strong className="block text-gray-500 dark:text-gray-400">Severity</strong> {caseItem.severity}</div>
                        <div><strong className="block text-gray-500 dark:text-gray-400">Owner</strong> {caseItem.owner || 'Unassigned'}</div>
                        <div><strong className="block text-gray-500 dark:text-gray-400">Created</strong> {new Date(caseItem.createdAt).toLocaleDateString()}</div>
                    </div>

                    {/* Threat Intel Enrichment */}
                    {caseItem.enrichmentData && caseItem.enrichmentData.length > 0 && (
                        <div>
                            <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2 flex items-center">
                                <ShieldSearchIcon size={14} className="mr-1.5" />
                                Threat Intelligence Enrichment
                            </h3>
                            <div className="space-y-2">
                                {caseItem.enrichmentData.map(result => <IntelResultCard key={result.id} result={result} />)}
                            </div>
                        </div>
                    )}

                    {/* Related Events */}
                    <div>
                        <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2 flex items-center">
                            <PaperclipIcon size={14} className="mr-1.5" />
                            Related Events ({(caseItem.relatedEvents || []).length})
                        </h3>
                        <div className="space-y-2">
                            {(caseItem.relatedEvents || []).map(event => (
                                <div key={event.id} className="p-2 bg-gray-50 dark:bg-gray-700/50 rounded-md text-xs">
                                    <p className="font-semibold text-gray-800 dark:text-gray-200">{event.description}</p>
                                    <p className="text-gray-500 dark:text-gray-400">{new Date(event.timestamp).toLocaleString(undefined, { timeZone })} | Host: {event.source.hostname}</p>
                                </div>
                            ))}
                            {(!caseItem.relatedEvents || caseItem.relatedEvents.length === 0) && (
                                <div className="text-xs text-gray-400 italic">No related events linked.</div>
                            )}
                        </div>
                    </div>

                    {/* Activity & Comments */}
                    <div className="pt-2">
                        <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2 flex items-center">
                            <MessageSquareQuoteIcon size={14} className="mr-1.5" />
                            Activity & Comments
                        </h3>
                        <div className="space-y-4">
                            {(caseItem.comments || []).map(comment => (
                                <div key={comment.id} className="flex items-start space-x-3">
                                    <img src={findUserAvatar(comment.user)} alt={comment.user} className="h-8 w-8 rounded-full object-cover" />
                                    <div className="flex-1">
                                        <div className="bg-gray-100 dark:bg-gray-700 rounded-lg p-3 text-sm">
                                            <div className="flex justify-between items-baseline">
                                                <p className="font-semibold text-gray-800 dark:text-gray-200">{comment.user}</p>
                                                <p className="text-xs text-gray-500 dark:text-gray-400 flex items-center">
                                                    <ClockIcon size={12} className="mr-1" />
                                                    {new Date(comment.timestamp).toLocaleString(undefined, { timeZone })}
                                                </p>
                                            </div>
                                            <p className="mt-1 text-gray-700 dark:text-gray-300">{comment.content}</p>
                                        </div>
                                    </div>
                                </div>
                            ))}
                            <div ref={commentsEndRef} />
                        </div>
                    </div>
                </div>

                {/* Add Comment Form */}
                {canManageCases && (
                    <div className="flex-shrink-0 mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                        <form onSubmit={handleSubmitComment} className="flex items-start space-x-3">
                            <img src={currentUser?.avatar} alt={currentUser?.name} className="h-8 w-8 rounded-full object-cover" />
                            <div className="flex-1">
                                <textarea
                                    value={newComment}
                                    onChange={(e) => setNewComment(e.target.value)}
                                    placeholder="Add a comment..."
                                    rows={2}
                                    className="w-full text-sm p-2 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                                />
                                <div className="flex justify-end mt-2">
                                    <button
                                        type="submit"
                                        disabled={!newComment.trim()}
                                        className="px-4 py-1.5 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 focus:outline-none disabled:bg-primary-400 disabled:cursor-not-allowed"
                                    >
                                        Add Comment
                                    </button>
                                </div>
                            </div>
                        </form>
                    </div>
                )}

                <div className="flex-shrink-0 mt-6 flex justify-between items-center pt-4 border-t border-gray-200 dark:border-gray-700">
                    {canInvestigate ? (
                        <button type="button" onClick={() => onAnalyzeImpact('case', caseItem.id)}
                            className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 flex items-center">
                            <Share2Icon size={16} className="mr-2" />
                            Analyze Impact
                        </button>
                    ) : (
                        <div></div> // Placeholder to keep layout consistent
                    )}
                    <button type="button" onClick={onClose}
                        className="px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm hover:bg-gray-50 dark:hover:bg-gray-600">
                        Close
                    </button>
                </div>
            </div>
        </div>
    );
};
