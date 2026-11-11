import React, { useState } from 'react';
import { Modal } from './Modal';
import { PLAN_KEYS } from '../services/plansApi';
import { ErrorBlock } from './PartnerCustomerModals';

interface AddNewTenantModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** May reject: the modal then stays open with the typed values and shows the refusal (UI-SPEC S3). */
  onSave: (tenantData: { name: string; subscriptionTier: string; maxAgents?: number }) => void | Promise<void>;
}

export const AddNewTenantModal: React.FC<AddNewTenantModalProps> = ({ isOpen, onClose, onSave }) => {
  const [tenantName, setTenantName] = useState('');
  const [subscriptionTier, setSubscriptionTier] = useState<string>('Free');
  // Custom is set per tenant by contract (D-24): its seats are asked for here.
  const [seats, setSeats] = useState('');
  const [seatsError, setSeatsError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  const planHelp = subscriptionTier === 'Free'
    ? 'Starts a free trial today. Seats and screens follow the Free plan.'
    : subscriptionTier === 'Custom'
      ? 'Set per tenant by contract. Tick screens one by one in Manage Tenant.'
      : `Seats and screens follow the ${subscriptionTier} plan. Tick screens one by one in Manage Tenant.`;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (tenantName.trim()) {
      const custom = subscriptionTier === 'Custom';
      if (custom && (!/^\d+$/.test(seats.trim()) || Number(seats) > 1_000_000)) {
        setSeatsError('Seats must be a whole number from 0 to 1,000,000.');
        return;
      }
      setSeatsError('');
      setSubmitError('');
      setIsSubmitting(true);
      try {
        await onSave({ name: tenantName.trim(), subscriptionTier, ...(custom ? { maxAgents: Number(seats) } : {}) });
        setTenantName('');
        setSeats('');
        onClose();
      } catch (error) {
        // Stay open with every typed value; the server's sentence is shown as sent.
        setSubmitError(error instanceof Error && error.message.trim()
          ? error.message : "Couldn't create the tenant. Check your connection and try again.");
      } finally {
        setIsSubmitting(false);
      }
    }
  };

  const footer = (
    <>
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
        form="add-tenant-form"
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
    </>
  );

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Add New Tenant" size="md" footer={footer}>
      <form id="add-tenant-form" onSubmit={handleSubmit}>
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
            <label htmlFor="subscriptionTier" className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Plan</label>
            <select
              id="subscriptionTier"
              aria-describedby="subscriptionTierHelp"
              value={subscriptionTier}
              onChange={(e) => setSubscriptionTier(e.target.value)}
              className="block w-full px-4 py-3 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-xl shadow-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent text-gray-900 dark:text-white transition-all"
            >
              {PLAN_KEYS.map(key => <option key={key} value={key}>{key}</option>)}
            </select>
            <p id="subscriptionTierHelp" className="mt-2 text-xs text-gray-500 dark:text-gray-400">{planHelp}</p>
          </div>

          {subscriptionTier === 'Custom' && (
            <div>
              <label htmlFor="tenantSeats" className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Seats</label>
              <input
                type="number"
                id="tenantSeats"
                min={0}
                max={1000000}
                step={1}
                value={seats}
                onChange={(e) => setSeats(e.target.value)}
                required
                className="block w-full px-4 py-3 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-xl shadow-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent text-gray-900 dark:text-white transition-all"
                placeholder="e.g., 40"
                aria-describedby="tenantSeatsHelp"
              />
              <p id="tenantSeatsHelp" className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                The seat limit from the contract. 0 means no computer can enroll.
              </p>
              {seatsError && <p role="alert" className="mt-2 text-sm text-red-600 dark:text-red-400">{seatsError}</p>}
            </div>
          )}
          {submitError && <ErrorBlock>{submitError}</ErrorBlock>}
        </div>
      </form>
    </Modal>
  );
};
