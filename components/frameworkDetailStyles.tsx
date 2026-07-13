import React from 'react';
import { ControlStatus } from '../types';
import { ClipboardListIcon, BuildingIcon, ShieldLockIcon, BinocularsIcon, ShieldIcon, SirenIcon, MessageSquareWarningIcon, HeartHandshakeIcon, ScaleIcon, UsersIcon, LayersIcon, ActivityIcon, RefreshCwIcon, DatabaseIcon, BrainCircuitIcon, ShieldCheckIcon } from './icons';

export const statusClasses: Record<ControlStatus, string> = {
  Implemented: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
  'In Progress': 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
  'Not Implemented': 'bg-gray-200 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
  'At Risk': 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
};

// Merged category classes for all frameworks
export const categoryClasses: Record<string, string> = {
  // HIPAA
  'Administrative Safeguard': 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
  'Physical Safeguard': 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300',
  'Technical Safeguard': 'bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-300',
  // NIST CSF
  'Identify': 'bg-sky-100 text-sky-800 dark:bg-sky-900/50 dark:text-sky-300',
  'Protect': 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
  'Detect': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300',
  'Respond': 'bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300',
  'Recover': 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/50 dark:text-indigo-300',
  // ISO 42001 (AI)
  'AI Policy': 'bg-fuchsia-100 text-fuchsia-800 dark:bg-fuchsia-900/50 dark:text-fuchsia-300',
  'Internal Organization': 'bg-violet-100 text-violet-800 dark:bg-violet-900/50 dark:text-violet-300',
  'Resources': 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900/50 dark:text-cyan-300',
  'Impact Assessment': 'bg-rose-100 text-rose-800 dark:bg-rose-900/50 dark:text-rose-300',
  'AI System Lifecycle': 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-300',
  'Data for AI': 'bg-sky-100 text-sky-800 dark:bg-sky-900/50 dark:text-sky-300',
  'Third Party': 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
  'Use of AI Systems': 'bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-300',
  // GDPR
  'Principles': 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/50 dark:text-indigo-300',
  'Rights of the Data Subject': 'bg-pink-100 text-pink-800 dark:bg-pink-900/50 dark:text-pink-300',
  'Controller and Processor': 'bg-slate-100 text-slate-800 dark:bg-slate-900/50 dark:text-slate-300',
  'Security of Personal Data': 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
  'Transfers': 'bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300',
};

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
