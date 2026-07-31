/**
 * Phase 30 (plan 30-06) invariant tests for QuestionnaireAnswerReviewPanel:
 *  1. EVIDENCE-SHOWN — source evidence (source + content) renders beside the answer.
 *  2. INSUFFICIENT-EVIDENCE — ungrounded drafts show the manual-drafting notice,
 *     never a confident-looking answer.
 *  3. RBAC-HIDDEN — non-reviewer roles get no Approve/Reject/Mark-Submitted controls.
 *  4. RBAC-SHOWN + DECISION-MAP — reviewers see actions on pending_review drafts and
 *     Request Changes maps to the backend decision string `needs_revision`.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// ---------------------------------------------------------------------------
// Mocks — registered BEFORE the component import
// ---------------------------------------------------------------------------
let mockRole = 'viewer';
vi.mock('../../contexts/UserContext', () => ({
  useUser: () => ({ currentUser: { role: mockRole, name: 'Test User' } }),
}));

vi.mock('../../utils/toast', () => ({
  showToast: vi.fn(),
}));

const decideDraftReview = vi.fn().mockResolvedValue({});
const createDraftReview = vi.fn().mockResolvedValue({ id: 'qar-1', draftId: 'qad-1', status: 'pending', created_at: '', updated_at: '' });
vi.mock('../../services/apiService', () => ({
  listDraftReviews: vi.fn().mockResolvedValue([]),
  createDraftReview: (...args: unknown[]) => createDraftReview(...args),
  decideDraftReview: (...args: unknown[]) => decideDraftReview(...args),
  submitAnswerDraft: vi.fn().mockResolvedValue({}),
}));

vi.mock('lucide-react', () => ({
  Check: () => null,
  X: () => null,
  MessageSquareWarning: () => null,
  Send: () => null,
  AlertTriangle: () => null,
}));

import { QuestionnaireAnswerReviewPanel } from '../../components/QuestionnaireAnswerReviewPanel';
import type { AnswerDraftDoc } from '../../services/apiService';

const GROUNDED_DRAFT: AnswerDraftDoc = {
  id: 'qad-1',
  tenantId: 'tenant-a',
  questionSetId: 'qni-1',
  questionId: 'q-1',
  questionText: 'Do you encrypt data at rest?',
  answerText: 'Yes, all data is encrypted at rest with AES-256.',
  confidence: 'high',
  sourceEvidenceIds: ['soc2-report.pdf', 'kms-policy.md'],
  sourceEvidence: [
    { source: 'soc2-report.pdf', content: 'Encryption at rest verified by auditor.' },
    { source: 'kms-policy.md', content: 'All volumes use AES-256 via KMS.' },
  ],
  status: 'pending_review',
};

const UNGROUNDED_DRAFT: AnswerDraftDoc = {
  ...GROUNDED_DRAFT,
  id: 'qad-2',
  answerText: '',
  confidence: 'insufficient_evidence',
  sourceEvidenceIds: [],
  sourceEvidence: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  mockRole = 'viewer';
});

describe('QuestionnaireAnswerReviewPanel', () => {
  it('renders every source evidence entry (source + content) beside the answer', () => {
    render(<QuestionnaireAnswerReviewPanel draft={GROUNDED_DRAFT} />);
    expect(screen.getByText('soc2-report.pdf')).toBeTruthy();
    expect(screen.getByText('Encryption at rest verified by auditor.')).toBeTruthy();
    expect(screen.getByText('kms-policy.md')).toBeTruthy();
    expect(screen.getByText('All volumes use AES-256 via KMS.')).toBeTruthy();
    expect(screen.getByText('Yes, all data is encrypted at rest with AES-256.')).toBeTruthy();
  });

  it('shows the manual-drafting notice for insufficient-evidence drafts, not a confident answer', () => {
    render(<QuestionnaireAnswerReviewPanel draft={UNGROUNDED_DRAFT} />);
    expect(screen.getByText(/Insufficient evidence — needs manual drafting/)).toBeTruthy();
    expect(screen.queryByText('Drafted answer')).toBeNull();
  });

  it('hides all decision and submit controls from non-reviewer roles', () => {
    mockRole = 'viewer';
    render(<QuestionnaireAnswerReviewPanel draft={GROUNDED_DRAFT} />);
    expect(screen.queryByText('Approve')).toBeNull();
    expect(screen.queryByText('Reject')).toBeNull();
    expect(screen.queryByText('Request Changes')).toBeNull();
    expect(screen.queryByText('Mark Submitted')).toBeNull();
  });

  it('shows actions to reviewers and maps Request Changes to needs_revision', async () => {
    mockRole = 'admin';
    render(<QuestionnaireAnswerReviewPanel draft={GROUNDED_DRAFT} />);
    fireEvent.click(screen.getByText('Request Changes'));
    fireEvent.change(screen.getByPlaceholderText('Comment (required)...'), {
      target: { value: 'Please cite the DR runbook too.' },
    });
    fireEvent.click(screen.getByText('Confirm Request Changes'));
    await waitFor(() => expect(decideDraftReview).toHaveBeenCalled());
    expect(createDraftReview).toHaveBeenCalledWith('qad-1');
    const [draftId, reviewId, decision] = decideDraftReview.mock.calls[0];
    expect(draftId).toBe('qad-1');
    expect(reviewId).toBe('qar-1');
    expect(decision).toBe('needs_revision');
  });
});
