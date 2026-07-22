import React, { useState } from 'react';
import { Modal } from './Modal';

export const AddControlModal = ({ isOpen, onClose, onAdd }: { isOpen: boolean; onClose: () => void; onAdd: (data: any) => void }) => {
  const [formData, setFormData] = useState({ id: '', name: '', description: '', category: '' });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onAdd(formData);
    setFormData({ id: '', name: '', description: '', category: '' });
  };

  const inputCls = "mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 dark:bg-gray-700 dark:border-gray-600 sm:text-sm px-3 py-2";
  const labelCls = "block text-sm font-medium text-gray-700 dark:text-gray-300";

  const footer = (
    <>
      <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md dark:bg-gray-700 dark:text-gray-300">Cancel</button>
      <button type="submit" form="add-control-form" className="px-4 py-2 text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 rounded-md">Add Control</button>
    </>
  );

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Add New Control" size="md" footer={footer}>
      <form id="add-control-form" onSubmit={handleSubmit}>
        <div className="space-y-4">
          <div>
            <label className={labelCls}>Control ID</label>
            <input type="text" required value={formData.id} onChange={e => setFormData({ ...formData, id: e.target.value })} className={inputCls} placeholder="e.g., CC1.1" />
          </div>
          <div>
            <label className={labelCls}>Name</label>
            <input type="text" required value={formData.name} onChange={e => setFormData({ ...formData, name: e.target.value })} className={inputCls} placeholder="Control Name" />
          </div>
          <div>
            <label className={labelCls}>Description</label>
            <textarea value={formData.description} onChange={e => setFormData({ ...formData, description: e.target.value })} className={inputCls} rows={3} />
          </div>
          <div>
            <label className={labelCls}>Category</label>
            <input type="text" value={formData.category} onChange={e => setFormData({ ...formData, category: e.target.value })} className={inputCls} placeholder="Category" />
          </div>
        </div>
      </form>
    </Modal>
  );
};
