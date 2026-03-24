import React, { useState, useEffect, useRef } from 'react';
import { BotIcon, XIcon, PlayIcon, PauseIcon, Volume2Icon } from './icons';
import { AppView } from '../types';

interface VoiceBotDemoProps {
    currentUser: any;
    currentView: AppView;
    setCurrentView: (view: AppView) => void;
}

interface TourStep {
    text: string;
    targetView?: AppView;
    highlightSelector?: string;
    delayAfter?: number;
}

export const VoiceBotDemo: React.FC<VoiceBotDemoProps> = ({ currentUser, currentView, setCurrentView }) => {
    const [isActive, setIsActive] = useState(false);
    const [isSpeaking, setIsSpeaking] = useState(false);
    const [currentStep, setCurrentStep] = useState(0);
    const [isDismissed, setIsDismissed] = useState(false);

    const synthRef = useRef<SpeechSynthesis | null>(null);
    const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

    // Initialize the tour script
    const getTourScript = (): TourStep[] => [
        {
            text: `Beep boop! Greetings, ${currentUser?.name || 'Human Owner'}! I am Chitti, your overly enthusiastic AI guide. Welcome to the future of enterprise operations!`,
            delayAfter: 1500
        },
        {
            text: `Look at this beautiful dashboard! It's so full of data, I might just overheat my neural network processing it all.`,
            targetView: 'dashboard',
            delayAfter: 2000
        },
        {
            text: `Let me show you our Agents. These little digital minions do all the hard work for you.`,
            targetView: 'agents',
            highlightSelector: '[title="Agents"]',
            delayAfter: 2000
        },
        {
            text: `You can download zip packages, install them on your servers, and boom! Complete visibility. Much better than staring at terminal screens all day, right?`,
            targetView: 'agents',
            delayAfter: 3000
        },
        {
            text: `We also have Security and Compliance features! We keep the bad guys out and the auditors happy. Which, frankly, is the hardest job of all.`,
            targetView: 'security',
            highlightSelector: '[title="Security Overview"]',
            delayAfter: 2500
        },
        {
            text: `And don't forget the Insights! My AI brethren are always analyzing your data to predict the future. We're like digital fortune tellers, but with math!`,
            targetView: 'proactiveInsights',
            highlightSelector: '[title="Proactive Insights"]',
            delayAfter: 2500
        },
        {
            text: `That concludes my express tour! Feel free to click around. If you break anything... well, just don't tell the Super Admin. Have fun exploring!`,
            targetView: 'dashboard',
            delayAfter: 1000
        }
    ];

    const script = getTourScript();

    useEffect(() => {
        if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
            synthRef.current = window.speechSynthesis;
        }

        // Check if user already dismissed it previously
        const hasCompleted = localStorage.getItem('genesis_tour_completed');
        if (hasCompleted) {
            setIsDismissed(true);
        }
    }, []);

    // Cleanup speech on unmount
    useEffect(() => {
        return () => {
            if (synthRef.current) {
                synthRef.current.cancel();
            }
        };
    }, []);

    const playStep = (stepIndex: number) => {
        if (!synthRef.current) return;

        const step = script[stepIndex];
        if (!step) {
            endTour();
            return;
        }

        // 1. Navigation & Highlighting
        if (step.targetView && step.targetView !== currentView) {
            setCurrentView(step.targetView);
        }

        // Remove old highlights
        document.querySelectorAll('.tour-highlight').forEach(el => el.classList.remove('tour-highlight'));

        // Add new highlight
        if (step.highlightSelector) {
            setTimeout(() => {
                const el = document.querySelector(step.highlightSelector);
                if (el) {
                    el.classList.add('tour-highlight');
                    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            }, 300); // Wait for transition
        }

        // 2. Speech Synthesis
        synthRef.current.cancel(); // Stop current speech

        const utterance = new SpeechSynthesisUtterance(step.text);

        // Try to find a good Indian English voice, or fallback to UK/US
        const voices = synthRef.current.getVoices();
        const preferredVoice = voices.find(v => v.lang === 'en-IN' || v.lang === 'hi-IN' || v.name.toLowerCase().includes('india'))
            || voices.find(v => v.name.includes('Google UK English Male') || v.name.includes('Samantha') || v.name.includes('Daniel') || v.lang === 'en-US');
        if (preferredVoice) utterance.voice = preferredVoice;

        utterance.rate = 1.05; // Slightly faster
        utterance.pitch = 1.1; // Slightly higher/friendly

        utterance.onstart = () => setIsSpeaking(true);

        utterance.onend = () => {
            setIsSpeaking(false);

            // Move to next step after delay
            setTimeout(() => {
                if (isActive) {
                    setCurrentStep(prev => prev + 1);
                }
            }, step.delayAfter || 1000);
        };

        utterance.onerror = (e) => {
            console.error('Speech synthesis error:', e);
            setIsSpeaking(false);
            // Fallback: move to next step anyway if speech fails
            setTimeout(() => {
                if (isActive) setCurrentStep(prev => prev + 1);
            }, 3000);
        };

        utteranceRef.current = utterance;
        synthRef.current.speak(utterance);
    };

    // React to step changes
    useEffect(() => {
        if (isActive && currentStep < script.length) {
            playStep(currentStep);
        } else if (isActive && currentStep >= script.length) {
            endTour();
        }
    }, [currentStep, isActive]);

    const startTour = () => {
        setIsActive(true);
        setIsDismissed(false);
        setCurrentStep(0);

        // Initialize voices (Chrome requires this to be triggered by user interaction)
        if (synthRef.current && synthRef.current.getVoices().length === 0) {
            synthRef.current.speak(new SpeechSynthesisUtterance(''));
            synthRef.current.cancel();
        }
    };

    const pauseResumeTour = () => {
        if (!synthRef.current) return;

        if (synthRef.current.paused) {
            synthRef.current.resume();
            setIsSpeaking(true);
        } else if (synthRef.current.speaking) {
            synthRef.current.pause();
            setIsSpeaking(false);
        }
    };

    const endTour = () => {
        setIsActive(false);
        setIsSpeaking(false);
        setCurrentStep(0);
        if (synthRef.current) synthRef.current.cancel();
        document.querySelectorAll('.tour-highlight').forEach(el => el.classList.remove('tour-highlight'));
        localStorage.setItem('genesis_tour_completed', 'true');
        setIsDismissed(true);
    };

    if (isDismissed && !isActive) return null;

    return (
        <div className="fixed bottom-24 right-6 z-50 flex flex-col items-end pointer-events-none">

            {/* Speech Bubble */}
            {isActive && currentStep < script.length && (
                <div className="bg-white dark:bg-gray-800 rounded-2xl rounded-br-sm shadow-2xl p-4 mb-4 max-w-sm border border-primary-500/30 transform transition-all duration-300 animate-in fade-in slide-in-from-bottom-4 pointer-events-auto relative overflow-hidden">
                    <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-primary-500 to-indigo-500"></div>
                    <p className="text-sm text-gray-700 dark:text-gray-200 leading-relaxed font-medium">
                        "{script[currentStep]?.text}"
                    </p>

                    {/* Controls */}
                    <div className="flex items-center justify-between mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
                        <span className="text-xs text-gray-400 font-semibold uppercase tracking-wider">
                            Step {currentStep + 1}/{script.length}
                        </span>
                        <div className="flex space-x-2">
                            <button
                                onClick={pauseResumeTour}
                                className="p-1.5 text-gray-500 hover:text-primary-500 hover:bg-primary-50 dark:hover:bg-primary-900/20 rounded-md transition-colors"
                            >
                                {synthRef.current?.paused ? <PlayIcon size={14} /> : <PauseIcon size={14} />}
                            </button>
                            <button
                                onClick={endTour}
                                className="p-1.5 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-md transition-colors"
                            >
                                <XIcon size={14} />
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Default CTA Bubble (if not active) */}
            {!isActive && !isDismissed && (
                <div className="bg-white dark:bg-gray-800 rounded-2xl rounded-br-sm shadow-lg p-3 mb-4 border border-gray-200 dark:border-gray-700 animate-bounce pointer-events-auto">
                    <p className="text-sm text-gray-700 dark:text-gray-300">
                        Hey! New here? <br /> Let me show you around! 👇
                    </p>
                </div>
            )}

            {/* Bot Avatar */}
            <button
                onClick={isActive ? pauseResumeTour : startTour}
                className={`relative group flex items-center justify-center w-14 h-14 rounded-full shadow-lg shadow-primary-500/30 pointer-events-auto transition-all duration-300
                    ${isSpeaking ? 'bg-gradient-to-tr from-primary-500 to-indigo-500 scale-110' : 'bg-gray-800 dark:bg-gray-700 hover:bg-primary-600'}
                `}
            >
                {/* Voice Animation Rings */}
                {isSpeaking && (
                    <>
                        <div className="absolute inset-0 rounded-full border-2 border-primary-400 animate-ping opacity-75"></div>
                        <div className="absolute inset-0 rounded-full border-2 border-indigo-400 animate-ping opacity-50 animation-delay-200"></div>
                    </>
                )}

                <Volume2Icon
                    size={24}
                    className={`text-white transition-transform duration-300 ${isSpeaking ? 'scale-110' : 'group-hover:scale-110'}`}
                />

                {/* Close badge */}
                {!isActive && (
                    <div
                        onClick={(e) => { e.stopPropagation(); endTour(); }}
                        className="absolute -top-1 -right-1 bg-red-500 text-white rounded-full p-0.5 hover:bg-red-600 opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                        <XIcon size={12} />
                    </div>
                )}
            </button>
        </div>
    );
};
