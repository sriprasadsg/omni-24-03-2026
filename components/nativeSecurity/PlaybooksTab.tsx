import React, { useEffect, useState } from 'react';
import {
  fetchRemediationPlaybooks, createRemediationPlaybook, updateRemediationPlaybook, deleteRemediationPlaybook,
} from '../../services/apiService';
import { RemediationPlaybook } from '../../types';
import { showToast } from '../../utils/toast';

const EMPTY_FORM = {
  name: '',
  finding_class: 'vuln',
  steps: '[\n  {"action": "kill_process", "params": {"target": "{{finding.resource_id}}"}, "destructive": true}\n]',
  rollback: '[]',
};

export function PlaybooksTab() {
  const [playbooks, setPlaybooks] = useState<RemediationPlaybook[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setPlaybooks(await fetchRemediationPlaybooks());
    } catch (e: any) {
      setError(e?.message || 'Failed to load playbooks');
    } finally {
      setLoading(false);
    }
  }

  function startEdit(pb: RemediationPlaybook) {
    setEditingId(pb.id);
    setForm({
      name: pb.name,
      finding_class: pb.finding_class,
      steps: JSON.stringify(pb.steps, null, 2),
      rollback: JSON.stringify(pb.rollback || [], null, 2),
    });
    setShowForm(true);
  }

  function startCreate() {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setShowForm(true);
  }

  async function handleSave() {
    let steps: any[];
    let rollback: any[];
    try {
      steps = JSON.parse(form.steps);
      rollback = JSON.parse(form.rollback);
    } catch {
      showToast('Steps and rollback must be valid JSON arrays', 'error');
      return;
    }
    setSaving(true);
    try {
      const body = { name: form.name, finding_class: form.finding_class, match: {}, steps, rollback };
      if (editingId) {
        await updateRemediationPlaybook(editingId, body);
      } else {
        await createRemediationPlaybook(body);
      }
      showToast('Playbook saved.', 'success');
      setShowForm(false);
      await load();
    } catch (e: any) {
      showToast(e?.message || 'Failed to save playbook', 'error');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(pb: RemediationPlaybook) {
    if (!window.confirm(`Delete playbook "${pb.name}"?`)) return;
    try {
      await deleteRemediationPlaybook(pb.id);
      showToast('Playbook deleted.', 'success');
      await load();
    } catch (e: any) {
      showToast(e?.message || 'Failed to delete playbook (vendored playbooks are read-only)', 'error');
    }
  }

  return (
    <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium">Remediation Playbooks</h3>
        <button
          onClick={startCreate}
          className="bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-medium px-3 py-1.5 rounded-lg"
        >
          New Playbook
        </button>
      </div>

      {loading && <p className="text-gray-400 text-sm">Loading playbooks…</p>}
      {error && !loading && <p className="text-red-400 text-sm">{error}</p>}

      {!loading && !error && (
        <div className="space-y-2 mb-4">
          {playbooks.map((pb) => (
            <div key={pb.id} className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 flex items-center justify-between flex-wrap gap-2">
              <div>
                <p className="text-sm font-medium">
                  {pb.name}
                  {pb.source === 'vendored' && (
                    <span className="ml-2 text-xs text-gray-500 border border-gray-700 rounded px-1.5 py-0.5">vendored</span>
                  )}
                </p>
                <p className="text-gray-500 text-xs mt-0.5">
                  {pb.finding_class} · {pb.steps.length} step{pb.steps.length === 1 ? '' : 's'}
                  {pb.steps.some((s) => s.destructive) ? ' · destructive' : ''}
                </p>
              </div>
              <div className="flex gap-2">
                {pb.source !== 'vendored' && (
                  <>
                    <button onClick={() => startEdit(pb)} className="text-cyan-400 hover:text-cyan-300 text-xs">Edit</button>
                    <button onClick={() => handleDelete(pb)} className="text-red-400 hover:text-red-300 text-xs">Delete</button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {showForm && (
        <div className="bg-gray-900 border border-gray-700 rounded-lg p-4 space-y-3">
          <h4 className="text-sm font-medium">{editingId ? 'Edit Playbook' : 'New Playbook'}</h4>
          <div className="flex gap-2">
            <input
              className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white flex-1"
              placeholder="Name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
            <input
              className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white flex-1"
              placeholder="Finding class (vuln / nscan / fim)"
              value={form.finding_class}
              onChange={(e) => setForm({ ...form, finding_class: e.target.value })}
            />
          </div>
          <div>
            <label className="text-xs text-gray-400">Steps (JSON array of {'{action, params, destructive}'})</label>
            <textarea
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-xs font-mono text-white mt-1"
              rows={5}
              value={form.steps}
              onChange={(e) => setForm({ ...form, steps: e.target.value })}
            />
          </div>
          <div>
            <label className="text-xs text-gray-400">Rollback (JSON array of {'{action, params}'}, optional)</label>
            <textarea
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-xs font-mono text-white mt-1"
              rows={3}
              value={form.rollback}
              onChange={(e) => setForm({ ...form, rollback: e.target.value })}
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleSave}
              disabled={saving || !form.name}
              className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-1.5 rounded-lg"
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
            <button
              onClick={() => setShowForm(false)}
              className="bg-gray-700 hover:bg-gray-600 text-white text-sm font-medium px-4 py-1.5 rounded-lg"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
