import React, { useState } from 'react';
import { XIcon } from './icons';

export const AddControlModal = ({ isOpen, onClose, onAdd }: { isOpen: boolean; onClose: () => void; onAdd: (data: any) => void }) => {
  const [formData, setFormData] = useState({ id: '', name: '', description: '', category: '' });

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onAdd(formData);
    setFormData({ id: '', name: '', description: '', category: '' });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-md">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-bold text-gray-900 dark:text-white">Add New Control</h3>
          <button onClick={onClose}><XIcon size={20} className="text-gray-500" /></button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Control ID</label>
              <input type="text" required value={formData.id} onChange={e => setFormData({ ...formData, id: e.target.value })} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 dark:bg-gray-700 dark:border-gray-600 sm:text-sm px-3 py-2" placeholder="e.g., CC1.1" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Name</label>
              <input type="text" required value={formData.name} onChange={e => setFormData({ ...formData, name: e.target.value })} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 dark:bg-gray-700 dark:border-gray-600 sm:text-sm px-3 py-2" placeholder="Control Name" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Description</label>
              <textarea value={formData.description} onChange={e => setFormData({ ...formData, description: e.target.value })} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 dark:bg-gray-700 dark:border-gray-600 sm:text-sm px-3 py-2" rows={3} />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Category</label>
              <input type="text" value={formData.category} onChange={e => setFormData({ ...formData, category: e.target.value })} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 dark:bg-gray-700 dark:border-gray-600 sm:text-sm px-3 py-2" placeholder="Category" />
            </div>
          </div>
          <div className="mt-6 flex justify-end space-x-3">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md dark:bg-gray-700 dark:text-gray-300">Cancel</button>
            <button type="submit" className="px-4 py-2 text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 rounded-md">Add Control</button>
          </div>
        </form>
      </div>
    </div>
  );
};
