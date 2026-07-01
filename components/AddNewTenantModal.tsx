import React, { useState } from 'react';

interface AddNewTenantModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (tenantData: { name: string; subscriptionTier: string }) => void;
}

export const AddNewTenantModal: React.FC<AddNewTenantModalProps> = ({ isOpen, onClose, onSave }) => {
  const [tenantName, setTenantName] = useState('');
  const [subscriptionTier, setSubscriptionTier] = useState('Enterprise');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (tenantName.trim()) {
      setIsSubmitting(true);
      try {
        await onSave({ name: tenantName.trim(), subscriptionTier });
        setTenantName('');
        onClose();
      } catch (error) {
        console.error("Failed to add tenant:", error);
      } finally {
        setIsSubmitting(false);
      }
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center backdrop-blur-sm" onClick={onClose}>
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-md p-8 m-4 border border-gray-200 dark:border-gray-700" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Add New Tenant</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="space-y-6">
            <div>
              <label htmlFor="tenantName" className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Company Name</label>
              <input
                type="text"
                id="tenantName"
                value={tenantName}
                onChange={(e) => setTenantName(e.target.value)}
                required
                className="block w-full px-4 py-3 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-xl shadow-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent text-gray-900 dark:text-white transition-all"
                placeholder="e.g., Acme Corporation"
              />
            </div>

            <div>
              <label htmlFor="subscriptionTier" className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Subscription Tier</label>
              <select
                id="subscriptionTier"
                value={subscriptionTier}
                onChange={(e) => setSubscriptionTier(e.target.value)}
                className="block w-full px-4 py-3 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-xl shadow-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent text-gray-900 dark:text-white transition-all"
              >
                <option value="Free">Free</option>
                <option value="Pro">Pro</option>
                <option value="Enterprise">Enterprise</option>
                <option value="Custom">Custom</option>
              </select>
            </div>
          </div>

          <div className="mt-8 flex justify-end space-x-4">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-6 py-2.5 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-xl shadow-sm hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-6 py-2.5 text-sm font-medium text-white bg-primary-600 rounded-xl hover:bg-primary-700 focus:outline-none shadow-lg shadow-primary-500/30 transition-all disabled:opacity-50 flex items-center"
            >
              {isSubmitting ? (
                <>
                  <svg className="animate-spin -ml-1 mr-3 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                  Creating...
                </>
              ) : 'Create Tenant'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
