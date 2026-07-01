import React from 'react';
import { LlmSettings as LlmSettingsType } from '../types';
import { DatabaseIcon, BrainCircuitIcon, CogIcon } from './icons';
import { VoiceBotSettingsPanel } from './VoiceBotSettingsPanel';
import { VoiceBotSettings } from '../types';

interface Props {
    llmSettings: LlmSettingsType | null;
    onOpenDb: () => void;
    onOpenLlm: () => void;
    onSaveVoiceBot: (settings: VoiceBotSettings) => void;
}

export function SettingsInfrastructureTab({ llmSettings, onOpenDb, onOpenLlm, onSaveVoiceBot }: Props) {
    return (
        <div className="space-y-6">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md border border-gray-200 dark:border-gray-700 p-6 flex flex-col md:flex-row justify-between items-start md:items-center">
                <div className="flex-grow">
                    <div className="flex items-center space-x-4">
                        <div className="flex-shrink-0"><DatabaseIcon size={32} className="text-primary-500" /></div>
                        <div>
                            <h4 className="text-lg font-bold text-gray-800 dark:text-gray-100">Database Connection</h4>
                            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">Configure the primary database connection for the platform.</p>
                        </div>
                    </div>
                </div>
                <div className="mt-4 md:mt-0 md:ml-6 flex-shrink-0">
                    <button onClick={onOpenDb} className="flex items-center px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-500 rounded-md shadow-sm hover:bg-gray-50 dark:hover:bg-gray-600">
                        <CogIcon size={16} className="mr-2" /> Configure
                    </button>
                </div>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md border border-gray-200 dark:border-gray-700 p-6 flex flex-col md:flex-row justify-between items-start md:items-center">
                <div className="flex-grow">
                    <div className="flex items-center space-x-4">
                        <div className="flex-shrink-0"><BrainCircuitIcon size={32} className="text-primary-500" /></div>
                        <div>
                            <h4 className="text-lg font-bold text-gray-800 dark:text-gray-100">LLM Provider</h4>
                            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">Manage the Large Language Model integration for AI features.</p>
                        </div>
                    </div>
                </div>
                <div className="mt-4 md:mt-0 md:ml-6 flex-shrink-0">
                    <button onClick={onOpenLlm} className="flex items-center px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-500 rounded-md shadow-sm hover:bg-gray-50 dark:hover:bg-gray-600">
                        <CogIcon size={16} className="mr-2" /> Configure
                    </button>
                </div>
            </div>
            <VoiceBotSettingsPanel
                settings={llmSettings?.voiceBotSettings || null}
                isAdmin={true}
                onSave={onSaveVoiceBot}
            />
        </div>
    );
}
