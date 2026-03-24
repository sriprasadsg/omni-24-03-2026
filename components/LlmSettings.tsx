

import React, { useState, useEffect } from 'react';
import { LlmSettings as LlmSettingsType } from '../types';
import { BrainCircuitIcon, XIcon, CogIcon, CheckIcon, AlertTriangleIcon, InfoIcon } from './icons';
import { GoogleGenAI } from '@google/genai';

interface LlmSettingsProps {
    isOpen: boolean;
    onClose: () => void;
    settings: LlmSettingsType;
    onSave: (settings: LlmSettingsType) => void;
}

const geminiModelDescriptions: Record<string, string> = {
    'gemini-2.5-pro': 'Most capable model for highly complex tasks like code generation, logical reasoning, and nuanced creative collaboration.',
    'gemini-2.0-flash': 'Fast and cost-efficient model for high-frequency tasks like summarization, chat applications, and data extraction.',
    'gemini-2.0-flash-lite': 'A lighter, faster version of Gemini Flash for simple tasks.',
    'gemini-2.5-flash-image': 'A model specialized for image generation and editing tasks.',
    'gemini-2.5-flash-native-audio-preview-09-2025': 'Optimized for real-time audio and video conversation tasks.',
    'gemini-2.5-flash-preview-tts': 'A model for high-quality text-to-speech generation.',
    'veo-3.1-fast-generate-preview': 'A model for general video generation tasks.',
    'imagen-4.0-generate-001': 'A model for high-quality, photorealistic image generation.',
};

const localModelDescriptions: Record<string, string> = {
    'local/llama3-8b': 'A powerful, locally-hosted Llama3 model with 8 billion parameters, suitable for a wide range of tasks.',
    'local/phi-3-mini': 'A lightweight, high-performance model from Microsoft, ideal for on-device and faster inference.',
    'omni-llm-v1': 'Your custom-built Transformer model trained from scratch on the platform. Fully offline, no internet access.',
};

const availableGeminiModels = Object.keys(geminiModelDescriptions);
const availableLocalModels = Object.keys(localModelDescriptions);


export const LlmSettings: React.FC<LlmSettingsProps> = ({ isOpen, onClose, settings, onSave }) => {
    const [formData, setFormData] = useState<LlmSettingsType>({ ...settings, provider: settings.provider || 'Gemini' });
    const [showKey, setShowKey] = useState(false);
    const [testStatus, setTestStatus] = useState<'idle' | 'testing' | 'success' | 'failed'>('idle');
    const [testMessage, setTestMessage] = useState('');
    const [customModels, setCustomModels] = useState<string[]>(settings.customModels || []);
    const [isAddingModel, setIsAddingModel] = useState(false);
    const [newModelName, setNewModelName] = useState('');

    useEffect(() => {
        if (isOpen) {
            setFormData({ ...settings, provider: settings.provider || 'Gemini' });
            setCustomModels(settings.customModels || []);
            setShowKey(false);
            setTestStatus('idle');
            setTestMessage('');
            setIsAddingModel(false);
            setNewModelName('');
        }
    }, [settings, isOpen]);

    const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
        const { name, value } = e.target;
        setFormData(prev => ({ ...prev, [name]: value }));
        setTestStatus('idle');
    };

    const handleSave = () => {
        onSave({ ...formData, customModels });
    };

    const handleAddModel = () => {
        if (newModelName && !availableGeminiModels.includes(newModelName) && !customModels.includes(newModelName)) {
            setCustomModels([...customModels, newModelName]);
            setFormData(prev => ({ ...prev, model: newModelName }));
            setIsAddingModel(false);
            setNewModelName('');
        }
    };

    const handleTestConnection = async () => {
        setTestStatus('testing');
        setTestMessage('');

        if (formData.provider === 'Local') {
            await new Promise(resolve => setTimeout(resolve, 1000));
            setTestStatus('success');
            setTestMessage(`Successfully connected to local model endpoint at ${formData.host || 'localhost'} (simulation).`);
            return;
        }

        try {
            if (!formData.apiKey || formData.apiKey.includes('*')) {
                throw new Error('A valid API key must be provided to run a test.');
            }
            const ai = new GoogleGenAI({ apiKey: formData.apiKey });
            const response = await ai.models.generateContent({
                model: 'gemini-2.0-flash', // Always test with a simple model
                contents: 'Say "test successful"',
            });

            if (response.text && response.text.toLowerCase().includes('test successful')) {
                setTestStatus('success');
                setTestMessage('Connection successful!');
            } else {
                throw new Error('Received an unexpected response from the API.');
            }
        } catch (error) {
            setTestStatus('failed');
            const errorMessage = error instanceof Error ? error.message : 'An unknown error occurred.';
            setTestMessage(`Connection failed: ${errorMessage}`);
            console.error(error);
        }
    };

    const allGeminiModels = [...availableGeminiModels, ...customModels];
    const availableModels = formData.provider === 'Local' ? availableLocalModels
        : formData.provider === 'Omni-LLM-Scratch' ? ['omni-llm-v1']
        : allGeminiModels;
    const modelDescriptions = formData.provider === 'Local' || formData.provider === 'Omni-LLM-Scratch' ? localModelDescriptions : geminiModelDescriptions;

    const renderField = (label: string, name: keyof LlmSettingsType, type: string = 'text', options?: string[]) => (
        <div>
            <label htmlFor={name} className="block text-sm font-medium text-gray-700 dark:text-gray-300">{label}</label>
            {options ? (
                <select id={name} name={name} value={String(formData[name])} onChange={handleChange}
                    className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm sm:text-sm"
                >
                    {options.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                </select>
            ) : (
                <input type={type} id={name} name={name} value={String(formData[name])} onChange={handleChange}
                    className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm sm:text-sm"
                />
            )}
        </div>
    );

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-lg p-6 m-4" onClick={e => e.stopPropagation()}>
                <div className="flex justify-between items-center mb-4">
                    <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center"><BrainCircuitIcon className="mr-3" /> LLM Provider Settings</h2>
                    <button onClick={onClose} className="p-1 rounded-full text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 focus:outline-none">
                        <XIcon size={20} />
                    </button>
                </div>
                <div className="space-y-4">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        {renderField('Provider', 'provider', 'select', ['Gemini', 'Local', 'Omni-LLM-Scratch'])}
                        <div>
                            <label htmlFor="model" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Preferred Model</label>
                            <div className="flex space-x-2">
                                {!isAddingModel ? (
                                    <>
                                        <select
                                            id="model"
                                            name="model"
                                            value={formData.model}
                                            onChange={handleChange}
                                            className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm sm:text-sm"
                                        >
                                            {availableModels.map(model => <option key={model} value={model}>{model}</option>)}
                                        </select>
                                        <button
                                            type="button"
                                            onClick={() => setIsAddingModel(true)}
                                            className="mt-1 px-3 py-2 bg-gray-100 dark:bg-gray-600 text-gray-600 dark:text-gray-300 rounded-md hover:bg-gray-200 dark:hover:bg-gray-500 text-sm font-medium whitespace-nowrap"
                                        >
                                            + Add New
                                        </button>
                                    </>
                                ) : (
                                    <>
                                        <input
                                            type="text"
                                            value={newModelName}
                                            onChange={(e) => setNewModelName(e.target.value)}
                                            placeholder="Enter model name (e.g., gemini-1.5-pro)"
                                            className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm sm:text-sm"
                                        />
                                        <button
                                            type="button"
                                            onClick={handleAddModel}
                                            className="mt-1 px-3 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700 text-sm font-medium"
                                        >
                                            Add
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => setIsAddingModel(false)}
                                            className="mt-1 px-3 py-2 bg-gray-200 dark:bg-gray-600 text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-300 dark:hover:bg-gray-500 text-sm font-medium"
                                        >
                                            Cancel
                                        </button>
                                    </>
                                )}
                            </div>
                        </div>
                    </div>
                    <div className="p-3 text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-700/50 rounded-md border border-gray-200 dark:border-gray-600 flex items-start">
                        <InfoIcon size={16} className="mr-2 mt-0.5 text-gray-400 flex-shrink-0" />
                        <div>
                            <span className="font-semibold text-gray-600 dark:text-gray-300">Model Info:</span>
                            <p>{modelDescriptions[formData.model] || 'Custom model. Ensure this model is available.'}</p>
                        </div>
                    </div>
                    {(formData.provider === 'Gemini') && (
                        <div>
                            <label htmlFor="apiKey" className="block text-sm font-medium text-gray-700 dark:text-gray-300">API Key</label>
                            <div className="relative mt-1">
                                <input
                                    type={showKey ? 'text' : 'password'}
                                    id="apiKey" name="apiKey"
                                    value={formData.apiKey}
                                    onChange={handleChange}
                                    className="block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm sm:text-sm"
                                    placeholder="Enter your Gemini API Key"
                                />
                                <button type="button" onClick={() => setShowKey(!showKey)} className="absolute inset-y-0 right-0 px-3 flex items-center text-sm text-gray-500">
                                    {showKey ? 'Hide' : 'Show'}
                                </button>
                            </div>
                            <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                                Don't have a key? <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noopener noreferrer" className="text-primary-600 dark:text-primary-400 hover:underline font-medium">Get an API key from Google AI Studio</a>.
                            </p>
                        </div>
                    )}
                    {formData.provider === 'Local' && (
                        <div>
                            <label htmlFor="host" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Local LLM Host</label>
                            <input
                                type="text"
                                id="host" name="host"
                                value={formData.host || ''}
                                onChange={handleChange}
                                placeholder="e.g., http://localhost:11434"
                                className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm sm:text-sm"
                            />
                            <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                                Enter the full URL of your local LLM API endpoint (e.g., Ollama, LM Studio).
                            </p>
                        </div>
                    )}
                    {formData.provider === 'Omni-LLM-Scratch' && (
                        <div className="p-3 bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-700/50 rounded-md text-xs text-blue-700 dark:text-blue-300">
                            <p className="font-bold mb-1">🧠 Omni-LLM (Custom Transformer)</p>
                            <p>This model was trained from scratch on the platform. It runs entirely offline with no external API calls. Navigate to <strong>AI &gt; LLMOps &gt; Train Custom Model</strong> to start or monitor training.</p>
                        </div>
                    )}
                </div>

                {testStatus !== 'idle' && (
                    <div className={`mt-4 p-3 rounded-md text-sm flex items-start ${testStatus === 'success' ? 'bg-green-50 dark:bg-green-900/50' :
                        testStatus === 'failed' ? 'bg-red-50 dark:bg-red-900/50' :
                            'bg-gray-100 dark:bg-gray-700/50'
                        }`}>
                        {testStatus === 'testing' && <CogIcon size={18} className="animate-spin mr-2 mt-0.5 text-gray-500" />}
                        {testStatus === 'success' && <CheckIcon size={18} className="mr-2 mt-0.5 text-green-500" />}
                        {testStatus === 'failed' && <AlertTriangleIcon size={18} className="mr-2 mt-0.5 text-red-500" />}
                        <p className={
                            testStatus === 'success' ? 'text-green-700 dark:text-green-300' :
                                testStatus === 'failed' ? 'text-red-700 dark:text-red-300' :
                                    'text-gray-500 dark:text-gray-400'
                        }>
                            {testStatus === 'testing' ? 'Testing connection...' : testMessage}
                        </p>
                    </div>
                )}

                <div className="mt-6 flex justify-between items-center pt-4 border-t border-gray-200 dark:border-gray-700">
                    <button
                        type="button"
                        onClick={handleTestConnection}
                        disabled={testStatus === 'testing'}
                        className="px-4 py-2 text-sm font-medium text-primary-700 bg-primary-100 dark:bg-primary-900/50 dark:text-primary-300 rounded-lg hover:bg-primary-200 dark:hover:bg-primary-900 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        Test Connection
                    </button>
                    <div className="flex space-x-3">
                        <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md">Cancel</button>
                        <button type="button" onClick={handleSave} className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">Save Changes</button>
                    </div>
                </div>
            </div>
        </div>
    );
};
