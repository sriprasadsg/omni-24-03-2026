import React, { useState, useEffect, useRef } from 'react';
import { VoiceBotSettings } from '../types';
import { Volume2Icon, PlayIcon, LoaderIcon } from './icons';

interface VoiceBotSettingsPanelProps {
    settings: VoiceBotSettings | null;
    onSave: (settings: VoiceBotSettings) => void;
    isAdmin: boolean;
}

export const VoiceBotSettingsPanel: React.FC<VoiceBotSettingsPanelProps> = ({ settings, onSave, isAdmin }) => {
    const defaultSettings: VoiceBotSettings = {
        enabled: true,
        voiceURI: '',
        pitch: 1.0,
        rate: 1.0,
    };

    const [currentSettings, setCurrentSettings] = useState<VoiceBotSettings>(settings || defaultSettings);
    const [availableVoices, setAvailableVoices] = useState<SpeechSynthesisVoice[]>([]);
    const [isPlaying, setIsPlaying] = useState(false);
    const [isSaving, setIsSaving] = useState(false);
    const synthRef = useRef<SpeechSynthesis | null>(null);

    useEffect(() => {
        if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
            synthRef.current = window.speechSynthesis;
            const loadVoices = () => {
                const voices = window.speechSynthesis.getVoices();
                if (voices.length > 0) {
                    setAvailableVoices(voices);
                    // Default to a good voice if none is set
                    if (!currentSettings.voiceURI) {
                        const defaultVoice = voices.find(v => v.name.includes('Google UK English Male') || v.name.includes('Daniel') || v.lang === 'en-US');
                        if (defaultVoice) {
                            setCurrentSettings(prev => ({ ...prev, voiceURI: defaultVoice.voiceURI }));
                        }
                    }
                }
            };

            loadVoices();
            if (window.speechSynthesis.onvoiceschanged !== undefined) {
                window.speechSynthesis.onvoiceschanged = loadVoices;
            }
        }
    }, []);

    const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
        const { name, value, type } = e.target;
        setCurrentSettings(prev => ({
            ...prev,
            [name]: type === 'checkbox' ? (e.target as HTMLInputElement).checked :
                type === 'range' ? parseFloat(value) : value
        }));
    };

    const handleTestVoice = () => {
        if (!synthRef.current || availableVoices.length === 0) return;

        synthRef.current.cancel();
        setIsPlaying(true);

        const utterance = new SpeechSynthesisUtterance("Hello! I am Chitti. How do I sound?");
        const selectedVoice = availableVoices.find(v => v.voiceURI === currentSettings.voiceURI);

        if (selectedVoice) utterance.voice = selectedVoice;
        utterance.pitch = currentSettings.pitch;
        utterance.rate = currentSettings.rate;

        utterance.onend = () => setIsPlaying(false);
        utterance.onerror = () => setIsPlaying(false);

        synthRef.current.speak(utterance);
    };

    const handleSave = async () => {
        setIsSaving(true);
        try {
            await onSave(currentSettings);
        } finally {
            setIsSaving(false);
        }
    };

    return (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md border border-gray-200 dark:border-gray-700 p-6 mb-6">
            <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-4">
                {isAdmin ? 'Global Voice Bot Settings' : 'Tenant Voice Bot Settings'}
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
                Configure the Chitti voice assistant {isAdmin ? 'for the entire platform' : 'for your tenant'}.
            </p>

            <div className="space-y-6">
                <div className="flex items-center justify-between">
                    <div>
                        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Enable Voice Bot</span>
                        <p className="text-xs text-gray-500 dark:text-gray-400">Allow users to interact using voice commands.</p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                        <input type="checkbox" name="enabled" checked={currentSettings.enabled} onChange={handleChange} className="sr-only peer" />
                        <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300 dark:peer-focus:ring-primary-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-primary-600"></div>
                    </label>
                </div>

                {currentSettings.enabled && (
                    <>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Voice Selection</label>
                            <select
                                name="voiceURI"
                                value={currentSettings.voiceURI}
                                onChange={handleChange}
                                className="block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                            >
                                {availableVoices.map(voice => (
                                    <option key={voice.voiceURI} value={voice.voiceURI}>
                                        {voice.name} ({voice.lang})
                                    </option>
                                ))}
                            </select>
                            {availableVoices.length === 0 && (
                                <p className="text-xs text-amber-500 mt-1">No voices found. Is your browser blocking Speech Synthesis?</p>
                            )}
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                    Pitch: {currentSettings.pitch.toFixed(1)}
                                </label>
                                <input
                                    type="range"
                                    name="pitch"
                                    min="0"
                                    max="2"
                                    step="0.1"
                                    value={currentSettings.pitch}
                                    onChange={handleChange}
                                    className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer dark:bg-gray-700"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                    Speed/Rate: {currentSettings.rate.toFixed(1)}
                                </label>
                                <input
                                    type="range"
                                    name="rate"
                                    min="0.5"
                                    max="2"
                                    step="0.1"
                                    value={currentSettings.rate}
                                    onChange={handleChange}
                                    className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer dark:bg-gray-700"
                                />
                            </div>
                        </div>

                        <div className="flex space-x-3 pt-4 border-t border-gray-200 dark:border-gray-700">
                            <button
                                type="button"
                                onClick={handleTestVoice}
                                disabled={isPlaying || availableVoices.length === 0}
                                className="flex items-center px-4 py-2 border border-gray-300 dark:border-gray-600 text-sm font-medium rounded-md text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:opacity-50"
                            >
                                {isPlaying ? <LoaderIcon size={16} className="mr-2 animate-spin" /> : <PlayIcon size={16} className="mr-2" />}
                                Test Voice
                            </button>
                            <button
                                type="button"
                                onClick={handleSave}
                                disabled={isSaving}
                                className="flex-1 flex justify-center items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:opacity-50"
                            >
                                {isSaving ? <LoaderIcon size={16} className="animate-spin mr-2" /> : <Volume2Icon size={16} className="mr-2" />}
                                Save Configuration
                            </button>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
};
