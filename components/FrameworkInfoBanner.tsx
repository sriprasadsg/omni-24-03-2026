import React from 'react';
import { ComplianceFramework } from '../types';
import { BookOpenCheckIcon, HeartPulseIcon, ShieldLockIcon, CreditCardIcon } from './icons';

const tones = {
  primary: { box: 'bg-primary-500/[0.06] ring-primary-500/20 text-primary-900 dark:text-primary-100', icon: 'text-primary-600 dark:text-primary-400' },
  blue: { box: 'bg-blue-500/[0.06] ring-blue-500/20 text-blue-900 dark:text-blue-100', icon: 'text-blue-600 dark:text-blue-400' },
  amber: { box: 'bg-amber-500/[0.08] ring-amber-500/25 text-amber-900 dark:text-amber-100', icon: 'text-amber-600 dark:text-amber-400' },
};

const Callout: React.FC<{ tone: keyof typeof tones; icon: React.ReactNode; title: string; children: React.ReactNode }> = ({ tone, icon, title, children }) => (
  <div className="px-5 pt-4">
    <div className={`p-3.5 rounded-xl ring-1 ring-inset flex items-start gap-3 text-sm ${tones[tone].box}`}>
      <span className={`flex-shrink-0 mt-0.5 ${tones[tone].icon}`}>{icon}</span>
      <div>
        <p className="font-semibold">{title}</p>
        <p className="mt-0.5 opacity-80">{children}</p>
      </div>
    </div>
  </div>
);

export const FrameworkInfoBanner: React.FC<{ framework: ComplianceFramework }> = ({ framework }) => {
  if (framework.id === 'nistcsf') {
    return (
      <Callout tone="primary" icon={<BookOpenCheckIcon size={18} />} title="Cybersecurity Risk Management">
        The NIST CSF provides a strategic, high-level framework for managing cybersecurity risk across the enterprise, structured around five core functions.
      </Callout>
    );
  }

  if (framework.id === 'hipaa' && framework.status !== 'Compliant') {
    return (
      <Callout tone="amber" icon={<HeartPulseIcon size={18} />} title="Business Associate Agreement (BAA) Required">
        Ensure a signed BAA is in place with all vendors and third parties that handle electronic Protected Health Information (ePHI).
      </Callout>
    );
  }

  if (framework.id === 'iso27001') {
    return (
      <Callout tone="blue" icon={<ShieldLockIcon size={18} />} title="Information Security Management System (ISMS)">
        These controls form the foundation of your ISMS, crucial for protecting organizational information assets.
      </Callout>
    );
  }

  if (framework.id === 'pci-dss') {
    return (
      <Callout tone="blue" icon={<CreditCardIcon size={18} />} title="Cardholder Data Environment (CDE) Protection">
        These controls are critical for protecting the CDE and ensuring the security of payment card transactions.
      </Callout>
    );
  }

  return null;
};
