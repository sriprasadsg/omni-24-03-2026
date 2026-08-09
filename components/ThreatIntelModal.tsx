

import React from 'react';
import { ThreatIntelResult } from '../types';
import { ShieldSearchIcon, CheckIcon, AlertTriangleIcon, ExternalLinkIcon } from './icons';
import { Modal } from './Modal';

interface ThreatIntelModalProps {
  isOpen: boolean;
  onClose: () => void;
  result: ThreatIntelResult | null;
}

const ResultDisplay: React.FC<{ result: ThreatIntelResult }> = ({ result }) => {
  const isMalicious = result.verdict === 'Malicious' || result.verdict === 'Suspicious';
  const detectionParts = result.detectionRatio.split('/');
  const positiveDetections = parseInt(detectionParts[0], 10);
  const totalEngines = parseInt(detectionParts[1], 10);
  const detectionPercentage = totalEngines > 0 ? (positiveDetections / totalEngines) * 100 : 0;

  // Provide fallback values
  const source = result.source || 'VirusTotal';
  const reportUrl = result.reportUrl || `https://www.virustotal.com/gui/search/${encodeURIComponent(result.artifact)}`;

  return (
    <div className="text-center">
      {isMalicious ? (
        <AlertTriangleIcon size={40} className="mx-auto text-red-500" />
      ) : (
        <CheckIcon size={40} className="mx-auto text-green-500" />
      )}
      <h3 className={`mt-3 text-xl font-bold ${isMalicious ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'}`}>
        {result.verdict}
      </h3>
      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
        Threat intelligence provided by <span className="font-semibold">{source}</span>.
      </p>
      <div className="mt-4 bg-gray-100 dark:bg-gray-700/50 rounded-lg p-4">
        <p className="text-2xl font-bold text-gray-800 dark:text-white">{result.detectionRatio}</p>
        <p className="text-sm text-gray-500 dark:text-gray-400">Detections</p>
        <div className="w-full bg-gray-200 dark:bg-gray-600 rounded-full h-2.5 mt-2">
          <div
            className={`h-2.5 rounded-full ${isMalicious ? 'bg-red-500' : 'bg-green-500'}`}
            style={{ width: `${detectionPercentage}%` }}
          ></div>
        </div>
      </div>
      <a href={reportUrl} target="_blank" rel="noopener noreferrer" className="mt-4 inline-flex items-center text-sm font-medium text-primary-600 dark:text-primary-400 hover:underline">
        View Full Report on VirusTotal <ExternalLinkIcon size={14} className="ml-1.5" />
      </a>
    </div>
  );
}

export const ThreatIntelModal: React.FC<ThreatIntelModalProps> = ({ isOpen, onClose, result }) => {
  if (!result) return null;

  const footer = (
    <button type="button" onClick={onClose}
      className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 focus:outline-none"
    >
      Close
    </button>
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      icon={<ShieldSearchIcon size={24} className="text-primary-500" />}
      title={
        <div>
          <h2 className="text-lg font-bold text-gray-900 dark:text-white">Threat Intelligence Scan</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 font-mono">{result.artifact}</p>
        </div>
      }
      size="md"
      footer={footer}
    >
      <div className="min-h-[200px] flex items-center justify-center">
        <ResultDisplay result={result} />
      </div>
    </Modal>
  );
};
