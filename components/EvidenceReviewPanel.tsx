import React, { useState, useEffect, useCallback } from 'react';
import { Check, X, MessageSquareWarning } from 'lucide-react';
import { useUser } from '../contexts/UserContext';
import { showToast } from '../utils/toast';
import { API_BASE, authFetch } from '../services/apiService';

const API = API_BASE || '/api';

const _REVIEWER_ROLES = ['admin', 'super_admin', 'compliance_reviewer'];

/** Extracts a safe, user-displayable string from a fetch error response body.
 * FastAPI's automatic validation-error responses put an *array* of error
 * objects in `detail` (not a string) — passing that directly to a toast
 * renderer that renders `{message}` as a JSX child crashes React entirely
 * ("Objects are not valid as a React child") instead of showing any message
 * (WR-03). */
const _errorDetail = (d: any, fallback: string): string =>
  typeof d?.detail === 'string' ? d.detail : fallback;

interface Review {
  id: string;
  evidenceId: string;
  reviewer: string;
  status: string;
  comment: string;
  created_at: string;
}

interface EvidenceReviewPanelProps {
  evidenceId: string;
  evidenceStatus?: string;
  onStatusChange?: () => void;
}

const STATUS_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  pending_review:    { bg: 'bg-amber-100 dark:bg-amber-900/30', text: 'text-amber-800 dark:text-amber-300', label: 'Pending Review' },
  approved:          { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-800 dark:text-green-300', label: 'Approved' },
  rejected:          { bg: 'bg-red-100 dark:bg-red-900/30',     text: 'text-red-800 dark:text-red-300',     label: 'Rejected' },
  needs_revision:    { bg: 'bg-amber-100 dark:bg-amber-900/30', text: 'text-amber-800 dark:text-amber-300', label: 'Needs Revision' },
};

// Review-thread entry statuses use the same semantic bg/text pairing as
// STATUS_STYLES (incl. dark mode) so a decided review's badge matches the
// parent evidence badge instead of drifting into its own color system.
const REVIEW_STATUS_STYLES: Record<string, { bg: string; text: string }> = {
  approved:          { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-800 dark:text-green-300' },
  rejected:          { bg: 'bg-red-100 dark:bg-red-900/30',     text: 'text-red-800 dark:text-red-300' },
  changes_requested: { bg: 'bg-amber-100 dark:bg-amber-900/30', text: 'text-amber-800 dark:text-amber-300' },
  pending:           { bg: 'bg-gray-100 dark:bg-gray-700',      text: 'text-gray-600 dark:text-gray-300' },
};

// Maps the internal button-click state (`action`) to the exact decision
// strings `UpdateDecisionRequest` on the backend validates against
// (`^(approved|rejected|changes_requested)$`). `action` itself must stay
// as the short internal labels so the button-active/placeholder/label
// logic elsewhere in this component keeps reading cleanly.
const DECISION_MAP: Record<'approve' | 'reject' | 'changes', string> = {
  approve: 'approved',
  reject: 'rejected',
  changes: 'changes_requested',
};

export const EvidenceReviewPanel: React.FC<EvidenceReviewPanelProps> = ({ evidenceId, evidenceStatus, onStatusChange }) => {
  const { currentUser } = useUser();
  const [reviews, setReviews] = useState<Review[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [hasFetchedOnce, setHasFetchedOnce] = useState(false);
  const [open, setOpen] = useState(false);
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [action, setAction] = useState<'approve' | 'reject' | 'changes' | ''>('');

  const isReviewer = currentUser && _REVIEWER_ROLES.includes(currentUser.role);
  const canSubmitForReview = !evidenceStatus || evidenceStatus === 'needs_revision' || evidenceStatus === 'rejected';

  const statStyle = evidenceStatus ? STATUS_STYLES[evidenceStatus] : null;

  // ── Fetch reviews ──────────────────────────────────────────────────────

  const fetchReviews = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await authFetch(`${API}/evidence/${evidenceId}/reviews`);
      if (!res.ok) { const d = await res.json().catch(() => ({})); setError(_errorDetail(d, 'Failed to load reviews')); return; }
      const data = await res.json();
      setReviews(data.reviews || []);
    } catch (err: any) {
      setError(err.message || 'Failed to load reviews');
    } finally {
      setLoading(false);
      setHasFetchedOnce(true);
    }
  }, [evidenceId]);

  // ── Submit for review ──────────────────────────────────────────────────

  const handleSubmitForReview = async () => {
    setSubmitting(true);
    try {
      const res = await authFetch(`${API}/evidence/${evidenceId}/submit-for-review`, { method: 'POST' });
      if (!res.ok) { const d = await res.json().catch(() => ({})); showToast(_errorDetail(d, 'Submit failed'), 'error'); return; }
      showToast('Evidence submitted for review', 'success');
      if (onStatusChange) onStatusChange();
    } catch (err: any) {
      showToast(err.message || 'Submit failed', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  // ── Submit review decision ─────────────────────────────────────────────

  const handleReviewDecision = async (decision: string) => {
    if ((decision === 'rejected' || decision === 'changes_requested') && !comment.trim()) {
      showToast('Comment required for this decision', 'error');
      return;
    }
    setSubmitting(true);
    try {
      // The create-review endpoint requires a non-empty comment (min_length=1).
      // When the reviewer leaves the field blank, send an explicitly synthetic
      // placeholder rather than a word ("Review") that reads as if the
      // reviewer actually typed it into a permanent audit-trail entry.
      const reviewRes = await authFetch(`${API}/evidence/${evidenceId}/review`, {
        method: 'POST',
        body: JSON.stringify({ comment: comment.trim() || '(no comment provided)' }),
      });
      if (!reviewRes.ok) { const d = await reviewRes.json().catch(() => ({})); showToast(_errorDetail(d, 'Failed to create review'), 'error'); return; }
      const { review } = await reviewRes.json();

      const patchRes = await authFetch(`${API}/evidence/${evidenceId}/review/${review.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ decision, comment: comment.trim() || '' }),
      });
      if (!patchRes.ok) { const d = await patchRes.json().catch(() => ({})); showToast(_errorDetail(d, 'Decision failed'), 'error'); return; }
      showToast(`Evidence ${decision}`, 'success');
      setComment('');
      setAction('');
      fetchReviews();
      if (onStatusChange) onStatusChange();
    } catch (err: any) {
      showToast(err.message || 'Decision failed', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  // ── Submit a new review record first, then patch decision ──────────────

  useEffect(() => { if (open) fetchReviews(); }, [open, fetchReviews]);

  return (
    <div className="mt-2 border-t border-gray-200 dark:border-gray-700 pt-2">
      {/* Status badge + toggle */}
      <div className="flex items-center gap-2 flex-wrap">
        {statStyle && (
          <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${statStyle.bg} ${statStyle.text}`}>
            {statStyle.label}
          </span>
        )}
        <button
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          className="text-xs text-blue-600 hover:text-blue-500 dark:text-blue-400 dark:hover:text-blue-300 font-medium"
        >
          {open ? 'Hide reviews' : (hasFetchedOnce ? `Reviews (${reviews.length})` : 'Show reviews')}
        </button>
        {canSubmitForReview && (
          <button
            onClick={handleSubmitForReview}
            disabled={submitting}
            className="text-xs px-3 py-3.5 rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50"
          >
            {submitting ? 'Submitting...' : 'Submit for Review'}
          </button>
        )}
      </div>

      {/* Reviews thread */}
      {open && (
        <div className="mt-2 space-y-2 pl-2 border-l-2 border-gray-200 dark:border-gray-600">
          {loading && <p className="text-xs text-gray-400 italic">Loading reviews...</p>}
          {error && <p className="text-xs text-red-500">{error}</p>}
          {!loading && !error && reviews.length === 0 && (
            <p className="text-xs text-gray-400 italic">No reviews yet.</p>
          )}
          {reviews.map((rv) => (
            <div key={rv.id} className="text-xs bg-gray-50 dark:bg-gray-800/50 rounded p-2">
              <div className="flex items-center gap-2 mb-1">
                <span className="font-medium text-gray-700 dark:text-gray-300">{rv.reviewer}</span>
                {(() => {
                  const rvStyle = REVIEW_STATUS_STYLES[rv.status] || REVIEW_STATUS_STYLES.pending;
                  return (
                    <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${rvStyle.bg} ${rvStyle.text}`}>
                      {rv.status.replace(/_/g, ' ')}
                    </span>
                  );
                })()}
                <span className="text-gray-400 ml-auto">{rv.created_at ? new Date(rv.created_at).toLocaleDateString() : ''}</span>
              </div>
              {rv.comment && <p className="text-gray-600 dark:text-gray-400">{rv.comment}</p>}
            </div>
          ))}

          {/* Reviewer actions — gated on pending_review to match the invariant
              create_review actually enforces server-side; without this gate,
              a reviewer could click Approve/Reject/Request-Changes on evidence
              that was never submitted (or already decided), guaranteeing a
              failed create_review call. */}
          {isReviewer && evidenceStatus === 'pending_review' && (
            <div className="mt-2 space-y-2">
              {!action && (
                <div className="flex gap-2">
                  <button onClick={() => setAction('approve')} className="flex items-center gap-1 px-3 py-3.5 text-xs rounded bg-green-600 hover:bg-green-700 text-white">
                    <Check size={14} aria-hidden="true" /> Approve
                  </button>
                  <button onClick={() => setAction('reject')} className="flex items-center gap-1 px-3 py-3.5 text-xs rounded bg-red-600 hover:bg-red-700 text-white">
                    <X size={14} aria-hidden="true" /> Reject
                  </button>
                  <button onClick={() => setAction('changes')} className="flex items-center gap-1 px-3 py-3.5 text-xs rounded bg-amber-500 hover:bg-amber-600 text-white">
                    <MessageSquareWarning size={14} aria-hidden="true" /> Request Changes
                  </button>
                </div>
              )}
              {action && (
                <div className="space-y-1">
                  <textarea
                    className="w-full text-xs p-1.5 border rounded dark:bg-gray-700 dark:border-gray-600"
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
                      onClick={() => action && handleReviewDecision(DECISION_MAP[action])}
                      disabled={submitting}
                      className="px-3 py-3.5 text-xs rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50"
                    >
                      {submitting ? 'Saving...' : `Confirm ${action === 'approve' ? 'Approve' : action === 'reject' ? 'Reject' : 'Request Changes'}`}
                    </button>
                    <button onClick={() => { setAction(''); setComment(''); }} className="px-3 py-3.5 text-xs rounded bg-gray-300 dark:bg-gray-600 text-gray-700 dark:text-gray-200">Cancel</button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
