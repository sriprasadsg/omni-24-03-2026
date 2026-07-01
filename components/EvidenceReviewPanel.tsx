import React, { useState, useEffect, useCallback } from 'react';
import { useUser } from '../contexts/UserContext';
import { showToast } from '../utils/toast';
import { API_BASE, authFetch } from '../services/apiService';

const API = API_BASE || '/api';

const _REVIEWER_ROLES = ['admin', 'super_admin', 'compliance_reviewer'];

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

export const EvidenceReviewPanel: React.FC<EvidenceReviewPanelProps> = ({ evidenceId, evidenceStatus, onStatusChange }) => {
  const { currentUser } = useUser();
  const [reviews, setReviews] = useState<Review[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(false);
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [action, setAction] = useState<'approve' | 'reject' | 'changes' | ''>('');

  const isReviewer = currentUser && _REVIEWER_ROLES.includes(currentUser.role);
  const canSubmitForReview = !evidenceStatus || evidenceStatus === 'needs_revision';

  const statStyle = evidenceStatus ? STATUS_STYLES[evidenceStatus] : null;

  // ── Fetch reviews ──────────────────────────────────────────────────────

  const fetchReviews = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await authFetch(`${API}/evidence/${evidenceId}/reviews`);
      if (!res.ok) { setError(`HTTP ${res.status}`); return; }
      const data = await res.json();
      setReviews(data.reviews || []);
    } catch (err: any) {
      setError(err.message || 'Failed to load reviews');
    } finally {
      setLoading(false);
    }
  }, [evidenceId]);

  // ── Submit for review ──────────────────────────────────────────────────

  const handleSubmitForReview = async () => {
    setSubmitting(true);
    try {
      const res = await authFetch(`${API}/evidence/${evidenceId}/submit-for-review`, { method: 'POST' });
      if (!res.ok) { const d = await res.json().catch(() => ({})); showToast(d.detail || 'Submit failed', 'error'); return; }
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
      const reviewRes = await authFetch(`${API}/evidence/${evidenceId}/review`, {
        method: 'POST',
        body: JSON.stringify({ comment: comment.trim() || 'Review' }),
      });
      if (!reviewRes.ok) { showToast('Failed to create review', 'error'); return; }
      const { review } = await reviewRes.json();

      const patchRes = await authFetch(`${API}/evidence/${evidenceId}/review/${review.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ decision, comment: comment.trim() || '' }),
      });
      if (!patchRes.ok) { const d = await patchRes.json().catch(() => ({})); showToast(d.detail || 'Decision failed', 'error'); return; }
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
          className="text-xs text-blue-600 hover:text-blue-500 dark:text-blue-400 dark:hover:text-blue-300 font-medium"
        >
          {open ? 'Hide reviews' : `Reviews (${reviews.length})`}
        </button>
        {canSubmitForReview && (
          <button
            onClick={handleSubmitForReview}
            disabled={submitting}
            className="text-xs px-2 py-1 rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50"
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
                <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                  rv.status === 'approved' ? 'bg-green-100 text-green-700' :
                  rv.status === 'rejected' ? 'bg-red-100 text-red-700' :
                  rv.status === 'changes_requested' ? 'bg-amber-100 text-amber-700' :
                  'bg-gray-100 text-gray-600'
                }`}>{rv.status.replace('_', ' ')}</span>
                <span className="text-gray-400 ml-auto">{rv.created_at ? new Date(rv.created_at).toLocaleDateString() : ''}</span>
              </div>
              {rv.comment && <p className="text-gray-600 dark:text-gray-400">{rv.comment}</p>}
            </div>
          ))}

          {/* Reviewer actions */}
          {isReviewer && (
            <div className="mt-2 space-y-2">
              {!action && (
                <div className="flex gap-1">
                  <button onClick={() => setAction('approve')} className="px-2 py-1 text-xs rounded bg-green-600 hover:bg-green-700 text-white">Approve</button>
                  <button onClick={() => setAction('reject')} className="px-2 py-1 text-xs rounded bg-red-600 hover:bg-red-700 text-white">Reject</button>
                  <button onClick={() => setAction('changes')} className="px-2 py-1 text-xs rounded bg-amber-500 hover:bg-amber-600 text-white">Request Changes</button>
                </div>
              )}
              {action && (
                <div className="space-y-1">
                  <textarea
                    className="w-full text-xs p-1.5 border rounded dark:bg-gray-700 dark:border-gray-600"
                    rows={2}
                    placeholder={action === 'approve' ? 'Optional comment...' : 'Comment (required)...'}
                    value={comment}
                    onChange={e => setComment(e.target.value)}
                  />
                  <div className="flex gap-1">
                    <button
                      onClick={() => handleReviewDecision(action === 'changes' ? 'changes_requested' : action)}
                      disabled={submitting}
                      className="px-2 py-1 text-xs rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50"
                    >
                      {submitting ? 'Saving...' : 'Confirm'}
                    </button>
                    <button onClick={() => { setAction(''); setComment(''); }} className="px-2 py-1 text-xs rounded bg-gray-300 dark:bg-gray-600 text-gray-700 dark:text-gray-200">Cancel</button>
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
