import React, { useState, useId } from 'react';
import { Modal } from './Modal';

export const AddControlModal = ({ isOpen, onClose, onAdd }: { isOpen: boolean; onClose: () => void; onAdd: (data: any) => void }) => {
  const [formData, setFormData] = useState({ id: '', name: '', description: '', category: '' });
  const fieldId = useId();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onAdd(formData);
    setFormData({ id: '', name: '', description: '', category: '' });
  };

  const inputCls = "block w-full h-9 px-3 text-sm rounded-xl text-gray-900 dark:text-white bg-white dark:bg-white/[0.04] border border-gray-200 dark:border-white/10 placeholder:text-gray-400 focus:outline-none focus:border-primary-500";
  const labelCls = "block text-[13px] font-medium text-gray-700 dark:text-gray-300 mb-1";

  const footer = (
    <>
      <button type="button" onClick={onClose} className="h-9 px-4 text-sm font-medium text-gray-700 dark:text-gray-200 glass rounded-xl">Cancel</button>
      <button type="submit" form="add-control-form" className="h-9 px-4 text-sm font-semibold text-white rounded-xl bg-primary-600 hover:bg-primary-700">Add Control</button>
    </>
  );

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Add New Control" size="md" footer={footer}>
      <form id="add-control-form" onSubmit={handleSubmit}>
        <div className="space-y-4">
          <div>
            <label htmlFor={`${fieldId}-id`} className={labelCls}>Control ID</label>
            <input id={`${fieldId}-id`} type="text" required value={formData.id} onChange={e => setFormData({ ...formData, id: e.target.value })} className={`${inputCls} font-mono`} placeholder="e.g., CC1.1" />
          </div>
          <div>
            <label htmlFor={`${fieldId}-name`} className={labelCls}>Name</label>
            <input id={`${fieldId}-name`} type="text" required value={formData.name} onChange={e => setFormData({ ...formData, name: e.target.value })} className={inputCls} placeholder="Control Name" />
          </div>
          <div>
            <label htmlFor={`${fieldId}-description`} className={labelCls}>Description</label>
            <textarea id={`${fieldId}-description`} value={formData.description} onChange={e => setFormData({ ...formData, description: e.target.value })} className={`${inputCls} h-auto py-2 resize-none`} rows={3} />
          </div>
          <div>
            <label htmlFor={`${fieldId}-category`} className={labelCls}>Category</label>
            <input id={`${fieldId}-category`} type="text" value={formData.category} onChange={e => setFormData({ ...formData, category: e.target.value })} className={inputCls} placeholder="Category" />
          </div>
        </div>
      </form>
    </Modal>
  );
};
