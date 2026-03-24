
import React, { useState, useEffect } from 'react';
import { AiSystem, User } from '../types';

interface AddAiSystemModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (data: Omit<AiSystem, 'id' | 'tenantId' | 'lastAssessmentDate' | 'fairnessMetrics' | 'impactAssessment' | 'risks' | 'documentation' | 'controls' | 'performanceData' | 'securityAlerts'>) => void;
  users: User[];
  systemToEdit: AiSystem | null;
}

type SystemStatus = 'Active' | 'In Development' | 'Sunset';
const statusOptions: SystemStatus[] = ['In Development', 'Active', 'Sunset'];

export const AddAiSystemModal: React.FC<AddAiSystemModalProps> = ({ isOpen, onClose, onSave, users, systemToEdit }) => {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [version, setVersion] = useState('1.0.0');
  const [owner, setOwner] = useState('');
  const [status, setStatus] = useState<SystemStatus>('In Development');

  const isEditing = !!systemToEdit;

  useEffect(() => {
    if (isOpen) {
      if (systemToEdit) {
        setName(systemToEdit.name);
        setDescription(systemToEdit.description);
        setVersion(systemToEdit.version);
        setOwner(systemToEdit.owner);
        setStatus(systemToEdit.status);
      } else {
        setName('');
        setDescription('');
        setVersion('1.0.0');
        setStatus('In Development');
        if (users.length > 0) {
          setOwner(users[0].name);
        } else {
          setOwner('');
        }
      }
    }
  }, [isOpen, systemToEdit, users]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !description.trim() || !version.trim() || !owner) {
      alert("Please fill all fields.");
      return;
    }

    let updatedSystemData = { name, description, version, owner, status };
    
    // Automatic Status Change Logic on Save
    if (isEditing && systemToEdit) {
        // From 'In Development' to 'Active'
        if (systemToEdit.status === 'In Development' && status === 'Active') {
            if (window.confirm('Promoting this system to "Active" will set its last assessment date to today. This is recommended for compliance. Continue?')) {
                (updatedSystemData as any).lastAssessmentDate = new Date().toISOString().split('T')[0];
            } else {
                return; // User cancelled
            }
        }
        // To 'Sunset'
        if (systemToEdit.status !== 'Sunset' && status === 'Sunset') {
             if (window.confirm('Setting the status to "Sunset" will disable its operational controls. This action is recommended for retired systems. Continue?')) {
                (updatedSystemData as any).controls = { ...systemToEdit.controls, isEnabled: false };
             } else {
                return; // User cancelled
             }
        }
    }

    onSave(updatedSystemData);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-lg p-6 m-4" onClick={e => e.stopPropagation()}>
        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">{isEditing ? 'Edit AI System' : 'Add New AI System'}</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="ai-name" className="block text-sm font-medium text-gray-700 dark:text-gray-300">System Name</label>
            <input type="text" id="ai-name" value={name} onChange={e => setName(e.target.value)} required 
                   className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm" />
          </div>
          <div>
            <label htmlFor="ai-description" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Description</label>
            <textarea id="ai-description" value={description} onChange={e => setDescription(e.target.value)} required rows={3}
                   className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label htmlFor="ai-version" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Version</label>
              <input type="text" id="ai-version" value={version} onChange={e => setVersion(e.target.value)} required 
                     className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm" />
            </div>
            <div>
              <label htmlFor="ai-status" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Status</label>
              <select id="ai-status" value={status} onChange={e => setStatus(e.target.value as SystemStatus)} className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm">
                {statusOptions.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label htmlFor="ai-owner" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Owner</label>
            <select id="ai-owner" value={owner} onChange={e => setOwner(e.target.value)} required className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm">
              <option value="">-- Select an Owner --</option>
              {users.map(user => <option key={user.id} value={user.name}>{user.name}</option>)}
            </select>
          </div>
          <div className="mt-6 flex justify-end space-x-3 pt-4 border-t border-gray-200 dark:border-gray-700">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md">Cancel</button>
            <button type="submit" className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">{isEditing ? 'Save Changes' : 'Add System'}</button>
          </div>
        </form>
      </div>
    </div>
  );
};
