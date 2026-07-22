import React, { useState, useEffect } from 'react';
import { SastFinding } from '../types';
import { CodeIcon, SparklesIcon, CogIcon } from './icons';
import { generateSastFix } from '../services/geminiService';
import { Modal } from './Modal';

interface SastFindingModalProps {
  isOpen: boolean;
  onClose: () => void;
  finding: SastFinding | null;
}

const CodeBlock: React.FC<{ code: string; language?: string }> = ({ code, language }) => (
    <pre className="bg-gray-900 text-white p-3 rounded-md text-xs whitespace-pre-wrap">
        <code className={`language-${language}`}>{code}</code>
    </pre>
);

export const SastFindingModal: React.FC<SastFindingModalProps> = ({ isOpen, onClose, finding }) => {
    const [isLoading, setIsLoading] = useState(false);
    const [fixedCode, setFixedCode] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (isOpen) {
            setIsLoading(false);
            setFixedCode(null);
            setError(null);
        }
    }, [isOpen]);

    const handleGenerateFix = async () => {
        if (!finding) return;
        setIsLoading(true);
        setError(null);
        setFixedCode(null);
        try {
            const result = await generateSastFix(finding);
            setFixedCode(result.fixedCode);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to generate fix.');
        } finally {
            setIsLoading(false);
        }
    };

    if (!finding) return null;

    const footer = (
        <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">
            Close
        </button>
    );

    return (
        <Modal
            isOpen={isOpen}
            onClose={onClose}
            icon={<CodeIcon className="text-primary-500" />}
            title={
                <div>
                    <span className="text-xl font-bold text-gray-900 dark:text-white">SAST Finding: {finding.type}</span>
                    <p className="text-sm text-gray-500 dark:text-gray-400 font-mono">{finding.fileName}:{finding.line}</p>
                </div>
            }
            size="3xl"
            footer={footer}
        >
                <div className="space-y-4">
                    <div>
                        <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">Vulnerable Code Snippet</h3>
                        <CodeBlock code={finding.codeSnippet} />
                    </div>

                    <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                        <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2 flex items-center">
                            <SparklesIcon size={16} className="mr-2 text-primary-500" />
                            AI-Powered Remediation
                        </h3>
                        {fixedCode && !isLoading && (
                            <div>
                                <p className="text-xs text-green-700 dark:text-green-300 mb-2">Suggested secure code:</p>
                                <CodeBlock code={fixedCode} />
                            </div>
                        )}
                        {isLoading && <div className="flex items-center text-sm text-gray-500"><CogIcon size={16} className="animate-spin mr-2" /> Generating fix...</div>}
                        {error && <p className="text-sm text-red-500">{error}</p>}
                        {!fixedCode && !isLoading && (
                            <button onClick={handleGenerateFix} className="flex items-center px-3 py-1.5 text-xs font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">
                                Generate AI Fix
                            </button>
                        )}
                    </div>
                </div>
        </Modal>
    );
};
