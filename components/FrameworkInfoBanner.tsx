import React from 'react';
import { ComplianceFramework } from '../types';
import { BookOpenCheckIcon, HeartPulseIcon, ShieldLockIcon, CreditCardIcon } from './icons';

export const FrameworkInfoBanner: React.FC<{ framework: ComplianceFramework }> = ({ framework }) => {
  if (framework.id === 'nistcsf') {
    return (
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <div className="p-3 bg-teal-50 dark:bg-teal-900/50 rounded-lg flex items-start text-sm text-teal-800 dark:text-teal-300 border border-teal-200 dark:border-teal-800">
          <BookOpenCheckIcon size={20} className="mr-2.5 mt-0.5 flex-shrink-0 text-teal-500" />
          <div>
            <span className="font-semibold">Cybersecurity Risk Management</span>
            <p className="text-teal-700 dark:text-teal-400">The NIST CSF provides a strategic, high-level framework for managing cybersecurity risk across the enterprise, structured around five core functions.</p>
          </div>
        </div>
      </div>
    );
  }

  if (framework.id === 'hipaa' && framework.status !== 'Compliant') {
    return (
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <div className="p-3 bg-amber-50 dark:bg-amber-900/50 rounded-lg flex items-start text-sm text-amber-800 dark:text-amber-300 border border-amber-200 dark:border-amber-800">
          <HeartPulseIcon size={20} className="mr-2.5 mt-0.5 flex-shrink-0 text-amber-500" />
          <div>
            <span className="font-semibold">Business Associate Agreement (BAA) Required</span>
            <p className="text-amber-700 dark:text-amber-400">Ensure a signed BAA is in place with all vendors and third parties that handle electronic Protected Health Information (ePHI).</p>
          </div>
        </div>
      </div>
    );
  }

  if (framework.id === 'iso27001') {
    return (
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <div className="p-3 bg-blue-50 dark:bg-blue-900/50 rounded-lg flex items-start text-sm text-blue-800 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
          <ShieldLockIcon size={20} className="mr-2.5 mt-0.5 flex-shrink-0 text-blue-500" />
          <div>
            <span className="font-semibold">Information Security Management System (ISMS)</span>
            <p className="text-blue-700 dark:text-blue-400">These controls form the foundation of your ISMS, crucial for protecting organizational information assets.</p>
          </div>
        </div>
      </div>
    );
  }

  if (framework.id === 'pci-dss') {
    return (
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <div className="p-3 bg-indigo-50 dark:bg-indigo-900/50 rounded-lg flex items-start text-sm text-indigo-800 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800">
          <CreditCardIcon size={20} className="mr-2.5 mt-0.5 flex-shrink-0 text-indigo-500" />
          <div>
            <span className="font-semibold">Cardholder Data Environment (CDE) Protection</span>
            <p className="text-indigo-700 dark:text-indigo-400">These controls are critical for protecting the CDE and ensuring the security of payment card transactions.</p>
          </div>
        </div>
      </div>
    );
  }

  return null;
};
