

import React, { useState, useEffect } from 'react';
import { CSPMFinding } from '../types';
import { XIcon, BotIcon, FileCodeIcon, CopyIcon, CheckIcon } from './icons';
import { generateCSPMRemediation, generateIacCode } from '../services/apiService';

interface CSPMRemediationModalProps {
  isOpen: boolean;
  onClose: () => void;
  finding: CSPMFinding | null;
}

const LoadingSkeleton: React.FC = () => (
    <div className="space-y-4 animate-pulse">
        <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/3"></div>
        <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-full"></div>
        <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-5/6"></div>
        <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/4 mt-4"></div>
        <div className="h-12 bg-gray-200 dark:bg-gray-700 rounded"></div>
    </div>
);

const FormattedMarkdown: React.FC<{ content: string }> = ({ content }) => {
    return (
        <div className="prose prose-sm dark:prose-invert max-w-none"
            dangerouslySetInnerHTML={{
                __html: content
                    .replace(/### (.*)/g, '<h3 class="text-sm font-semibold mt-4 mb-2">$1</h3>')
                    .replace(/```bash\n([\s\S]*?)\n```/g, '<pre class="bg-gray-900 text-white p-2 rounded-md text-xs"><code>$1</code></pre>')
                    .replace(/`([^`]+)`/g, '<code class="bg-gray-200 dark:bg-gray-700 px-1 py-0.5 rounded text-xs">$1</code>')
            }}
        />
    );
};

const CodeBlock: React.FC<{ code: string }> = ({ code }) => {
    const [copied, setCopied] = useState(false);

    const handleCopy = () => {
        navigator.clipboard.writeText(code).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        });
    };

    return (
        <div className="relative bg-gray-900 dark:bg-black rounded-md p-4 font-mono text-sm text-gray-200">
            <pre className="whitespace-pre-wrap break-all"><code>{code}</code></pre>
            <button
                onClick={handleCopy}
                className="absolute top-2 right-2 p-1.5 rounded-md bg-gray-700 hover:bg-gray-600 text-gray-300 focus:outline-none focus:ring-2 focus:ring-primary-500"
                aria-label="Copy code"
            >
                {copied ? <CheckIcon size={16} className="text-green-400" /> : <CopyIcon size={16} />}
            </button>
        </div>
    );
};

export const CSPMRemediationModal: React.FC<CSPMRemediationModalProps> = ({ isOpen, onClose, finding }) => {
  const [remediation, setRemediation] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');

  const [iacCode, setIacCode] = useState<string>('');
  const [isGeneratingIac, setIsGeneratingIac] = useState<boolean>(false);
  const [iacError, setIacError] = useState<string>('');

  useEffect(() => {
    if (isOpen) {
        setRemediation('');
        setIsLoading(false);
        setError('');
        setIacCode('');
        setIsGeneratingIac(false);
        setIacError('');
    }
  }, [isOpen]);

  const handleGenerate = async () => {
    if (!finding) return;
    setIsLoading(true);
    setError('');
    setRemediation('');
    try {
      const result = await generateCSPMRemediation(finding);
      setRemediation(result.remediation);
    } catch (err) {
      setError('Failed to generate remediation plan.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleGenerateIac = async () => {
    if (!finding) return;
    setIsGeneratingIac(true);
    setIacError('');
    setIacCode('');
    try {
        const result = await generateIacCode(finding);
        setIacCode(result.code);
    } catch(err) {
        setIacError('Failed to generate IaC code.');
    } finally {
        setIsGeneratingIac(false);
    }
  };


  if (!isOpen || !finding) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl p-6 m-4 max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="flex-shrink-0 flex justify-between items-start mb-4">
          <div>
            <h2 className="text-lg font-bold text-gray-900 dark:text-white">{finding.title}</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 font-mono">{finding.resourceId}</p>
          </div>
          <button onClick={onClose} className="p-1 rounded-full text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 focus:outline-none">
            <XIcon size={20} />
          </button>
        </div>
        <div className="flex-grow space-y-4 overflow-y-auto pr-2">
            <div>
                <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">Description</h3>
                <p className="mt-1 text-gray-600 dark:text-gray-300">{finding.description}</p>
            </div>
            <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2 flex items-center">
                    <BotIcon size={16} className="mr-2 text-primary-500" />
                    AI-Powered Remediation Plan
                </h3>
                {remediation && !isLoading && <FormattedMarkdown content={remediation} />}
                {isLoading && <LoadingSkeleton />}
                {error && <p className="text-red-500">{error}</p>}
                {!remediation && !isLoading && (
                    <div className="text-center py-4">
                        <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">Generate a step-by-step remediation guide using Gemini.</p>
                        <button onClick={handleGenerate} className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">
                            Generate Plan
                        </button>
                    </div>
                )}
            </div>
            <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2 flex items-center">
                    <FileCodeIcon size={16} className="mr-2 text-primary-500" />
                    AI-Generated Infrastructure as Code (IaC)
                </h3>
                {iacCode && !isGeneratingIac && <CodeBlock code={iacCode} />}
                {isGeneratingIac && <LoadingSkeleton />}
                {iacError && <p className="text-red-500">{iacError}</p>}
                {!iacCode && !isGeneratingIac && (
                    <div className="text-center py-4">
                        <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">Generate Terraform (HCL) code to remediate this finding.</p>
                        <button onClick={handleGenerateIac} className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">
                            Generate IaC
                        </button>
                    </div>
                )}
            </div>
        </div>
      </div>
    </div>
  );
};
