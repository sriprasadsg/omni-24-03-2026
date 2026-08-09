import React, { useState } from 'react';
import { Modal } from './Modal';

interface RiskFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: any) => Promise<void>;
}

export const RiskFormModal: React.FC<RiskFormModalProps> = ({ isOpen, onClose, onSubmit }) => {
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    category: 'Enterprise',
    status: 'Open',
    likelihood: 1,
    impact: 1,
    owner: '',
    residual_likelihood: 1,
    residual_impact: 1
  });
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await onSubmit(formData);
      onClose();
    } catch (error) {
      console.error("Failed to create risk", error);
    } finally {
      setSubmitting(false);
    }
  };

  const inputCls = "w-full rounded-lg border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white";
  const labelCls = "block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1";

  const footer = (
    <>
      <button type="button" onClick={onClose} className="px-4 py-2 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg">
        Cancel
      </button>
      <button type="submit" form="risk-form" disabled={submitting} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50">
        {submitting ? 'Creating...' : 'Create Risk'}
      </button>
    </>
  );

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="New Risk" size="lg" footer={footer}>
      <form id="risk-form" onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className={labelCls}>Title</label>
          <input type="text" required value={formData.title} onChange={e => setFormData({ ...formData, title: e.target.value })} className={inputCls} />
        </div>
        <div>
          <label className={labelCls}>Description</label>
          <textarea required value={formData.description} onChange={e => setFormData({ ...formData, description: e.target.value })} className={`${inputCls} h-24`} />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={labelCls}>Category</label>
            <select value={formData.category} onChange={e => setFormData({ ...formData, category: e.target.value })} className={inputCls}>
              <option value="Enterprise">Enterprise</option>
              <option value="AI">AI</option>
              <option value="Cyber">Cyber</option>
              <option value="Compliance">Compliance</option>
              <option value="Third-Party">Third-Party</option>
            </select>
          </div>
          <div>
            <label className={labelCls}>Owner</label>
            <input type="text" required value={formData.owner} onChange={e => setFormData({ ...formData, owner: e.target.value })} className={inputCls} />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={labelCls}>Likelihood (1-5)</label>
            <input type="number" min="1" max="5" value={formData.likelihood} onChange={e => setFormData({ ...formData, likelihood: parseInt(e.target.value) })} className={inputCls} />
          </div>
          <div>
            <label className={labelCls}>Impact (1-5)</label>
            <input type="number" min="1" max="5" value={formData.impact} onChange={e => setFormData({ ...formData, impact: parseInt(e.target.value) })} className={inputCls} />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={labelCls}>Residual Likelihood (1-5)</label>
            <input type="number" min="1" max="5" value={formData.residual_likelihood} onChange={e => setFormData({ ...formData, residual_likelihood: parseInt(e.target.value) })} className={inputCls} />
          </div>
          <div>
            <label className={labelCls}>Residual Impact (1-5)</label>
            <input type="number" min="1" max="5" value={formData.residual_impact} onChange={e => setFormData({ ...formData, residual_impact: parseInt(e.target.value) })} className={inputCls} />
          </div>
        </div>
      </form>
    </Modal>
  );
};
