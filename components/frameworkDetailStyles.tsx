import React from 'react';
import { ControlStatus } from '../types';
import { ClipboardListIcon, BuildingIcon, ShieldLockIcon, BinocularsIcon, ShieldIcon, SirenIcon, MessageSquareWarningIcon, HeartHandshakeIcon, ScaleIcon, UsersIcon, LayersIcon, ActivityIcon, RefreshCwIcon, DatabaseIcon, BrainCircuitIcon, ShieldCheckIcon } from './icons';

export const statusClasses: Record<ControlStatus, string> = {
  Implemented: 'text-emerald-700 dark:text-emerald-300 bg-emerald-500/10 ring-1 ring-inset ring-emerald-500/20',
  'In Progress': 'text-blue-700 dark:text-blue-300 bg-blue-500/10 ring-1 ring-inset ring-blue-500/20',
  'Not Implemented': 'text-gray-700 dark:text-gray-300 bg-gray-500/10 ring-1 ring-inset ring-gray-500/20',
  'At Risk': 'text-red-700 dark:text-red-300 bg-red-500/10 ring-1 ring-inset ring-red-500/20',
};

export const statusDots: Record<ControlStatus, string> = {
  Implemented: 'bg-emerald-500',
  'In Progress': 'bg-blue-500',
  'Not Implemented': 'bg-gray-400',
  'At Risk': 'bg-red-500',
};

// Colour is reserved for control status; a category is told apart by its icon and name.
export const categoryChip = 'text-gray-700 dark:text-gray-300 bg-gray-500/10 ring-1 ring-inset ring-gray-500/15';

export const categoryIcons: Record<string, React.ReactNode> = {
  // HIPAA
  'Administrative Safeguard': <ClipboardListIcon size={12} className="mr-1.5" />,
  'Physical Safeguard': <BuildingIcon size={12} className="mr-1.5" />,
  'Technical Safeguard': <ShieldLockIcon size={12} className="mr-1.5" />,
  // NIST CSF
  'Identify': <BinocularsIcon size={12} className="mr-1.5" />,
  'Protect': <ShieldIcon size={12} className="mr-1.5" />,
  'Detect': <SirenIcon size={12} className="mr-1.5" />,
  'Respond': <MessageSquareWarningIcon size={12} className="mr-1.5" />,
  'Recover': <HeartHandshakeIcon size={12} className="mr-1.5" />,
  // ISO 42001 (AI)
  'AI Policy': <ScaleIcon size={12} className="mr-1.5" />,
  'Internal Organization': <UsersIcon size={12} className="mr-1.5" />,
  'Resources': <LayersIcon size={12} className="mr-1.5" />,
  'Impact Assessment': <ActivityIcon size={12} className="mr-1.5" />,
  'AI System Lifecycle': <RefreshCwIcon size={12} className="mr-1.5" />,
  'Data for AI': <DatabaseIcon size={12} className="mr-1.5" />,
  'Third Party': <BuildingIcon size={12} className="mr-1.5" />,
  'Use of AI Systems': <BrainCircuitIcon size={12} className="mr-1.5" />,
  // GDPR
  'Principles': <ScaleIcon size={12} className="mr-1.5" />,
  'Rights of the Data Subject': <UsersIcon size={12} className="mr-1.5" />,
  'Controller and Processor': <BuildingIcon size={12} className="mr-1.5" />,
  'Security of Personal Data': <ShieldCheckIcon size={12} className="mr-1.5" />,
  'Transfers': <ActivityIcon size={12} className="mr-1.5" />,
};

export const statusOptions: (ControlStatus | 'All')[] = ['All', 'Implemented', 'In Progress', 'At Risk', 'Not Implemented'];
