import React, { useState, useEffect, useCallback } from 'react';
import { Check, X, MessageSquareWarning, Send, AlertTriangle } from 'lucide-react';
import { useUser } from '../contexts/UserContext';
import { showToast } from '../utils/toast';
import {
  AnswerDraftDoc,
  DraftReview,
  listDraftReviews,
  createDraftReview,
  decideDraftReview,
  submitAnswerDraft,
} from '../services/apiService';

// IN-01 (15-REVIEW.md pattern): kept in sync by hand with the equivalent
// literal in backend/questionnaire_answer_review_endpoints.py
// (_REVIEWER_ROLES). The backend always re-enforces authorization
// server-side regardless of this list, so drift here is a UI-confusion
// risk (mismatched button visibility), not an authz bypass.
const _REVIEWER_ROLES = ['admin', 'super_admin', 'compliance_reviewer'];

const STATUS_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  pending_review: { bg: 'bg-amber-100 dark:bg-amber-900/30', text: 'text-amber-800 dark:text-amber-300', label: 'Pending Review' },
  approved:       { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-800 dark:text-green-300', label: 'Approved' },
  rejected:       { bg: 'bg-red-100 dark:bg-red-900/30',     text: 'text-red-800 dark:text-red-300',     label: 'Rejected' },
  needs_revision: { bg: 'bg-amber-100 dark:bg-amber-900/30', text: 'text-amber-800 dark:text-amber-300', label: 'Needs Revision' },
  submitted:      { bg: 'bg-blue-100 dark:bg-blue-900/30',   text: 'text-blue-800 dark:text-blue-300',   label: 'Submitted' },
};

const CONFIDENCE_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  high:   { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-800 dark:text-green-300', label: 'High confidence' },
  medium: { bg: 'bg-blue-100 dark:bg-blue-900/30',   text: 'text-blue-800 dark:text-blue-300',   label: 'Medium confidence' },
  low:    { bg: 'bg-amber-100 dark:bg-amber-900/30', text: 'text-amber-800 dark:text-amber-300', label: 'Low confidence' },
  insufficient_evidence: { bg: 'bg-red-100 dark:bg-red-900/30', text: 'text-red-800 dark:text-red-300', label: 'Insufficient evidence' },
};

// Maps the internal button-click state to the exact decision strings the
// backend validates (`approved|rejected|needs_revision`). NOTE: this differs
// from EvidenceReviewPanel's `changes_requested` — the questionnaire review
// state machine uses `needs_revision`.
const DECISION_MAP: Record<'approve' | 'reject' | 'changes', 'approved' | 'rejected' | 'needs_revision'> = {
  approve: 'approved',
  reject: 'rejected',
  changes: 'needs_revision',
};

interface Props {
  draft: AnswerDraftDoc;
  onStatusChange?: () => void;
}

export const QuestionnaireAnswerReviewPanel: React.FC<Props> = ({ draft, onStatusChange }) => {
  const { currentUser } = useUser();
  const [reviews, setReviews] = useState<DraftReview[]>([]);
  const [showReviews, setShowReviews] = useState(false);
  const [hasFetchedOnce, setHasFetchedOnce] = useState(false);
  const [comment, setComment] = useState('');
  const [editedAnswer, setEditedAnswer] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [action, setAction] = useState<'approve' | 'reject' | 'changes' | ''>('');

  const isReviewer = !!currentUser && _REVIEWER_ROLES.includes(currentUser.role);
  const statStyle = STATUS_STYLES[draft.status] || STATUS_STYLES.pending_review;
  const confStyle = CONFIDENCE_STYLES[draft.confidence] || CONFIDENCE_STYLES.low;
  const isUngrounded = draft.sourceEvidence.length === 0 && draft.confidence === 'insufficient_evidence';

  const fetchReviews = useCallback(async () => {
    try {
      setReviews(await listDraftReviews(draft.id));
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : 'Failed to load reviews', 'error');
    } finally {
      setHasFetchedOnce(true);
    }
  }, [draft.id]);

  useEffect(() => { if (showReviews) fetchReviews(); }, [showReviews, fetchReviews]);

  const handleDecision = async (decision: 'approved' | 'rejected' | 'needs_revision') => {
    if ((decision === 'rejected' || decision === 'needs_revision') && !comment.trim()) {
      showToast('Comment required for this decision', 'error');
      return;
    }
    setSubmitting(true);
    try {
      const review = await createDraftReview(draft.id);
      await decideDraftReview(
        draft.id,
        review.id,
        decision,
        comment.trim() || '(no comment provided)',
        editedAnswer !== null && editedAnswer !== draft.answerText ? editedAnswer : undefined,
      );
      showToast(`Draft ${decision.replace(/_/g, ' ')}`, 'success');
      setComment('');
      setAction('');
      fetchReviews();
      if (onStatusChange) onStatusChange();
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : 'Decision failed', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      await submitAnswerDraft(draft.id);
      showToast('Answer marked submitted', 'success');
      if (onStatusChange) onStatusChange();
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : 'Submit failed', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-3 bg-white dark:bg-gray-800">
      {/* Header: question + badges */}
      <div className="flex items-start gap-2 flex-wrap">
        <h4 className="text-sm font-semibold text-gray-800 dark:text-gray-100 flex-1">{draft.questionText}</h4>
        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${statStyle.bg} ${statStyle.text}`}>
          {statStyle.label}
        </span>
        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${confStyle.bg} ${confStyle.text}`}>
          {confStyle.label}
        </span>
      </div>

      {/* Answer + grounding evidence — evidence is ALWAYS visible beside the
          answer BEFORE any approve control (AI-SPEC Critical Failure Mode #1:
          rubber-stamp approval because evidence wasn't shown). All strings are
          rendered as escaped React text children — evidence content is an
          untrusted injection surface (T-30-FE-03). */}
      {isUngrounded ? (
        <div className="mt-2 flex items-start gap-2 text-sm text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-900/20 rounded p-2">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
          <p>Insufficient evidence — needs manual drafting. No grounded answer was generated for this question.</p>
        </div>
      ) : (
        <div className="mt-2 grid gap-2 md:grid-cols-2">
          <div>
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Drafted answer</p>
            {isReviewer && draft.status === 'pending_review' ? (
              <textarea
                className="w-full text-sm p-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-gray-100"
                rows={4}
                value={editedAnswer !== null ? editedAnswer : draft.answerText}
                onChange={e => setEditedAnswer(e.target.value)}
                aria-label="Editable drafted answer"
              />
            ) : (
              <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">{draft.answerText}</p>
            )}
          </div>
          <div>
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
              Source evidence ({draft.sourceEvidence.length})
            </p>
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {draft.sourceEvidence.map((ev, i) => (
                <div key={i} className="text-xs bg-gray-50 dark:bg-gray-900/40 rounded p-2">
                  <p className="font-medium text-gray-700 dark:text-gray-300">{ev.source}</p>
                  <p className="text-gray-600 dark:text-gray-400 whitespace-pre-wrap">{ev.content}</p>
                </div>
              ))}
              {draft.sourceEvidence.length === 0 && (
                <p className="text-xs text-gray-400 italic">No source evidence attached.</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Review thread toggle */}
      <div className="mt-2 flex items-center gap-2 flex-wrap">
        <button
          onClick={() => setShowReviews(!showReviews)}
          aria-expanded={showReviews}
          className="text-xs text-blue-600 hover:text-blue-500 dark:text-blue-400 dark:hover:text-blue-300 font-medium"
        >
          {showReviews ? 'Hide reviews' : (hasFetchedOnce ? `Reviews (${reviews.length})` : 'Show reviews')}
        </button>
        {draft.reviewComment && (
          <span className="text-xs text-gray-500 dark:text-gray-400">Last review: {draft.reviewComment}</span>
        )}
      </div>

      {showReviews && (
        <div className="mt-2 space-y-1 pl-2 border-l-2 border-gray-200 dark:border-gray-600">
          {reviews.length === 0 && <p className="text-xs text-gray-400 italic">No reviews yet.</p>}
          {reviews.map(rv => (
            <div key={rv.id} className="text-xs bg-gray-50 dark:bg-gray-800/50 rounded p-2">
              <span className="font-medium text-gray-700 dark:text-gray-300">{rv.decided_by || 'pending'}</span>
              <span className="ml-2 text-gray-500">{rv.status}</span>
              {rv.comment && <p className="text-gray-600 dark:text-gray-400">{rv.comment}</p>}
            </div>
          ))}
        </div>
      )}

      {/* Reviewer decision controls — RBAC-gated defense-in-depth on top of the
          backend 403 (T-30-FE-01) and gated on pending_review to match the
          invariant create_review enforces server-side. */}
      {isReviewer && draft.status === 'pending_review' && (
        <div className="mt-3 space-y-2">
          {!action && (
            <div className="flex gap-2">
              <button onClick={() => setAction('approve')} className="flex items-center gap-1 px-3 py-1.5 text-xs rounded bg-green-600 hover:bg-green-700 text-white">
                <Check size={14} aria-hidden="true" /> Approve
              </button>
              <button onClick={() => setAction('reject')} className="flex items-center gap-1 px-3 py-1.5 text-xs rounded bg-red-600 hover:bg-red-700 text-white">
                <X size={14} aria-hidden="true" /> Reject
              </button>
              <button onClick={() => setAction('changes')} className="flex items-center gap-1 px-3 py-1.5 text-xs rounded bg-amber-500 hover:bg-amber-600 text-white">
                <MessageSquareWarning size={14} aria-hidden="true" /> Request Changes
              </button>
            </div>
          )}
          {action && (
            <div className="space-y-1">
              <textarea
                className="w-full text-xs p-1.5 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-gray-100"
                rows={2}
                maxLength={2000}
                placeholder={action === 'approve' ? 'Optional comment...' : 'Comment (required)...'}
                value={comment}
                onChange={e => setComment(e.target.value)}
              />
              {(action === 'reject' || action === 'changes') && (
                <p className="text-xs text-red-600 dark:text-red-400">
                  This decision is recorded in the permanent audit trail and cannot be undone.
                </p>
              )}
              <div className="flex gap-2">
                <button
                  onClick={() => action && handleDecision(DECISION_MAP[action])}
                  disabled={submitting}
                  className="px-3 py-1.5 text-xs rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50"
                >
                  {submitting ? 'Saving...' : `Confirm ${action === 'approve' ? 'Approve' : action === 'reject' ? 'Reject' : 'Request Changes'}`}
                </button>
                <button onClick={() => { setAction(''); setComment(''); }} className="px-3 py-1.5 text-xs rounded bg-gray-300 dark:bg-gray-600 text-gray-700 dark:text-gray-200">Cancel</button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Terminal transition: approved → submitted (RAG-02; no analog in
          EvidenceReviewPanel). Backend re-enforces the approved-only guard. */}
      {isReviewer && draft.status === 'approved' && (
        <div className="mt-3">
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="flex items-center gap-1 px-3 py-1.5 text-xs rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50"
          >
            <Send size={14} aria-hidden="true" /> {submitting ? 'Submitting...' : 'Mark Submitted'}
          </button>
        </div>
      )}
    </div>
  );
};
