import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Plus, Upload, Sparkles, RefreshCw } from 'lucide-react';
import { showToast } from '../utils/toast';
import {
  InboundQuestionnaireSet,
  AnswerDraftDoc,
  listInboundQuestionnaires,
  createInboundQuestionnaire,
  uploadInboundQuestionnaire,
  generateAnswerDrafts,
  listAnswerDrafts,
} from '../services/apiService';
import { QuestionnaireAnswerReviewPanel } from './QuestionnaireAnswerReviewPanel';

export const InboundQuestionnaireDashboard: React.FC = () => {
  const [sets, setSets] = useState<InboundQuestionnaireSet[]>([]);
  const [drafts, setDrafts] = useState<AnswerDraftDoc[]>([]);
  const [selectedSetId, setSelectedSetId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [creating, setCreating] = useState(false);
  const [generatingSetId, setGeneratingSetId] = useState<string | null>(null);
  const [uploadingSetId, setUploadingSetId] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [manualQuestions, setManualQuestions] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pendingUploadSetId = useRef<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [setList, allDrafts] = await Promise.all([
        listInboundQuestionnaires(),
        listAnswerDrafts(),
      ]);
      setSets(setList);
      // Keep approved drafts in the queue: "Mark Submitted" only renders on
      // an approved draft, so filtering to pending_review would make drafts
      // vanish at approval and leave submission unreachable from the UI.
      setDrafts(allDrafts.filter(d => d.status !== 'submitted'));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load questionnaires');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const handleCreate = async () => {
    if (!title.trim()) {
      showToast('Title is required', 'error');
      return;
    }
    setCreating(true);
    try {
      const questions = manualQuestions
        .split('\n')
        .map(l => l.trim())
        .filter(Boolean)
        .map(text => ({ text }));
      await createInboundQuestionnaire(title.trim(), questions.length ? questions : undefined);
      showToast('Questionnaire set created', 'success');
      setTitle('');
      setManualQuestions('');
      refresh();
    } catch (err: unknown) {
      // Surface backend 400s (e.g. ambiguous/unmapped column) — never swallow
      showToast(err instanceof Error ? err.message : 'Create failed', 'error');
    } finally {
      setCreating(false);
    }
  };

  const triggerUpload = (setId: string) => {
    pendingUploadSetId.current = setId;
    fileInputRef.current?.click();
  };

  const handleFileChosen = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    const setId = pendingUploadSetId.current;
    e.target.value = '';
    if (!file || !setId) return;
    setUploadingSetId(setId);
    try {
      const updated = await uploadInboundQuestionnaire(setId, file);
      showToast(`Uploaded — set now has ${updated.questions.length} questions`, 'success');
      refresh();
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : 'Upload failed', 'error');
    } finally {
      setUploadingSetId(null);
    }
  };

  const handleGenerate = async (set: InboundQuestionnaireSet) => {
    if (!set.questions.length) {
      showToast('This set has no questions — add or upload some first', 'error');
      return;
    }
    setGeneratingSetId(set.id);
    try {
      const generated = await generateAnswerDrafts(set);
      showToast(`Generated ${generated.length} draft answer${generated.length === 1 ? '' : 's'} for review`, 'success');
      refresh();
    } catch (err: unknown) {
      showToast(err instanceof Error ? err.message : 'Draft generation failed', 'error');
    } finally {
      setGeneratingSetId(null);
    }
  };

  const visibleDrafts = selectedSetId
    ? drafts.filter(d => d.questionSetId === selectedSetId)
    : drafts;

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-xl font-bold text-gray-800 dark:text-gray-100">Inbound Questionnaires</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Intake customer security questionnaires, auto-draft grounded answers, and review before submission.
          </p>
        </div>
        <button
          onClick={refresh}
          className="flex items-center gap-1 px-3 py-1.5 text-xs rounded bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-gray-600"
          aria-label="Refresh questionnaires and drafts"
        >
          <RefreshCw size={14} aria-hidden="true" /> Refresh
        </button>
      </div>

      {/* Intake form (RAG-01): manual entry + file upload */}
      <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-3 bg-white dark:bg-gray-800 space-y-2">
        <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100">New inbound questionnaire</h3>
        <input
          type="text"
          className="w-full text-sm p-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-gray-100"
          placeholder="Title (e.g. Acme Corp Vendor Security Questionnaire)"
          value={title}
          onChange={e => setTitle(e.target.value)}
        />
        <textarea
          className="w-full text-sm p-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-gray-100"
          rows={3}
          placeholder="Optional: questions, one per line. You can also upload an .xlsx/.csv after creating the set."
          value={manualQuestions}
          onChange={e => setManualQuestions(e.target.value)}
        />
        <button
          onClick={handleCreate}
          disabled={creating}
          className="flex items-center gap-1 px-3 py-1.5 text-xs rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50"
        >
          <Plus size={14} aria-hidden="true" /> {creating ? 'Creating...' : 'Create question set'}
        </button>
      </div>

      {/* Hidden shared file input for per-set uploads */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".xlsx,.csv"
        className="hidden"
        onChange={handleFileChosen}
        aria-label="Upload questionnaire file"
      />

      {/* Question set list */}
      <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-3 bg-white dark:bg-gray-800">
        <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-2">Question sets</h3>
        {loading && <p className="text-sm text-gray-400 italic">Loading...</p>}
        {error && <p className="text-sm text-red-500">{error}</p>}
        {!loading && !error && sets.length === 0 && (
          <p className="text-sm text-gray-400 italic">No questionnaire sets yet — create one above.</p>
        )}
        <div className="space-y-2">
          {sets.map(set => (
            <div
              key={set.id}
              className={`flex items-center gap-2 flex-wrap p-2 rounded border ${selectedSetId === set.id ? 'border-blue-400 dark:border-blue-500' : 'border-gray-100 dark:border-gray-700'}`}
            >
              <button
                onClick={() => setSelectedSetId(selectedSetId === set.id ? null : set.id)}
                className="text-sm font-medium text-gray-800 dark:text-gray-100 hover:text-blue-600 dark:hover:text-blue-400 text-left flex-1"
                aria-pressed={selectedSetId === set.id}
              >
                {set.title}
                <span className="ml-2 text-xs text-gray-500">({set.questions.length} questions)</span>
              </button>
              <button
                onClick={() => triggerUpload(set.id)}
                disabled={uploadingSetId === set.id}
                className="flex items-center gap-1 px-2 py-1 text-xs rounded bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-gray-600 disabled:opacity-50"
              >
                <Upload size={12} aria-hidden="true" /> {uploadingSetId === set.id ? 'Uploading...' : 'Upload .xlsx/.csv'}
              </button>
              <button
                onClick={() => handleGenerate(set)}
                disabled={generatingSetId === set.id}
                className="flex items-center gap-1 px-2 py-1 text-xs rounded bg-purple-600 hover:bg-purple-700 text-white disabled:opacity-50"
              >
                <Sparkles size={12} aria-hidden="true" /> {generatingSetId === set.id ? 'Generating...' : 'Generate draft answers'}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Review queue (RAG-02) */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100">
          Pending review{selectedSetId ? ' (selected set)' : ''} — {visibleDrafts.length}
        </h3>
        {!loading && visibleDrafts.length === 0 && (
          <p className="text-sm text-gray-400 italic">No drafts awaiting review.</p>
        )}
        {visibleDrafts.map(draft => (
          <QuestionnaireAnswerReviewPanel key={draft.id} draft={draft} onStatusChange={refresh} />
        ))}
      </div>
    </div>
  );
};
