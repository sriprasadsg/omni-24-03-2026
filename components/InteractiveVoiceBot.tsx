import React, { useState, useEffect, useRef } from 'react';
import { MicIcon, XIcon, Volume2Icon, LoaderIcon } from './icons';
import { AppView, VoiceBotSettings } from '../types';
import { getChatAssistantResponse } from '../services/apiService';

interface InteractiveVoiceBotProps {
    currentUser: any;
    currentView: AppView;
    setCurrentView: (view: AppView) => void;
    voiceBotSettings?: VoiceBotSettings | null;
}

// Ensure TypeScript knows about window.SpeechRecognition
declare global {
    interface Window {
        SpeechRecognition: any;
        webkitSpeechRecognition: any;
    }
}

export const InteractiveVoiceBot: React.FC<InteractiveVoiceBotProps> = ({ currentUser, currentView, setCurrentView, voiceBotSettings }) => {
    // UI States
    const [isActive, setIsActive] = useState(false);
    const [isDismissed, setIsDismissed] = useState(false);

    // Bot States
    const [botState, setBotState] = useState<'idle' | 'listening' | 'thinking' | 'speaking'>('idle');
    const [transcript, setTranscript] = useState('');
    const [aiResponse, setAiResponse] = useState('');
    const [displayText, setDisplayText] = useState(`Hey ${currentUser?.name?.split(' ')[0] || 'there'}! I'm Chitti. Say "Hey Chitti" or click me to start!`);

    // Wake Word Detection state
    const [isWakeWordEnabled, setIsWakeWordEnabled] = useState(true);

    // Refs for native APIs and lifecycle management
    const recognitionRef = useRef<any>(null);
    const backgroundRecognitionRef = useRef<any>(null);
    const synthRef = useRef<SpeechSynthesis | null>(null);
    const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
    
    const isBackgroundStarting = useRef(false);
    const isMainStarting = useRef(false);

    // provide a state ref so handlers can read the latest values
    const aiResponseRef = useRef(aiResponse);
    useEffect(() => { aiResponseRef.current = aiResponse; }, [aiResponse]);

    // --- Safe Wrappers for Speech Recognition ---

    const stopBackground = () => {
        isBackgroundStarting.current = false;
        try { backgroundRecognitionRef.current?.stop(); } catch (e) {}
    };

    const startBackground = () => {
        // Prevent starting if already active or busy
        if (!isWakeWordEnabled || isActive || isDismissed || botState !== 'idle' || isBackgroundStarting.current) return;
        try {
            isBackgroundStarting.current = true;
            backgroundRecognitionRef.current?.start();
        } catch (e) {
            isBackgroundStarting.current = false;
        }
    };

    const stopMain = () => {
        isMainStarting.current = false;
        try { recognitionRef.current?.stop(); } catch (e) {}
    };

    const startMain = () => {
        if (isMainStarting.current) return;
        try {
            isMainStarting.current = true;
            recognitionRef.current?.start();
            // botState is updated in onstart
        } catch (e) {
            isMainStarting.current = false;
        }
    };

    // --- Initialize Native APIs ---

    useEffect(() => {
        if (typeof window !== 'undefined') {
            if ('speechSynthesis' in window) {
                synthRef.current = window.speechSynthesis;
            }

            const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (SpeechRec) {
                // 1. Main Recognition Setup
                const recognition = new SpeechRec();
                recognition.continuous = false;
                recognition.interimResults = true;
                recognition.lang = 'en-IN';

                recognition.onstart = () => {
                    isMainStarting.current = false;
                    setBotState('listening');
                    setDisplayText("Listening...");
                };

                recognition.onresult = (event: any) => {
                    let currentTranscript = '';
                    for (let i = event.resultIndex; i < event.results.length; i++) {
                        currentTranscript += event.results[i][0].transcript;
                    }
                    setTranscript(currentTranscript);
                    setDisplayText(currentTranscript);
                };

                recognition.onerror = (event: any) => {
                    isMainStarting.current = false;
                    console.error('[VoiceBot] Main recognition error:', event.error);
                    if (event.error === 'aborted') {
                        setDisplayText("Connection lost. Retrying assistant...");
                        setTimeout(() => setBotState('idle'), 1500);
                    } else if (event.error !== 'no-speech') {
                        setBotState('idle');
                        setDisplayText("I missed that. Could you repeat?");
                    } else {
                        setBotState('idle');
                    }
                };

                recognition.onend = () => {
                    isMainStarting.current = false;
                    setBotState(prev => {
                        if (prev === 'listening') return 'thinking';
                        return prev;
                    });
                };
                recognitionRef.current = recognition;

                // 2. Background Recognition Setup
                const backgroundRec = new SpeechRec();
                backgroundRec.continuous = true;
                backgroundRec.interimResults = true;
                backgroundRec.lang = 'en-IN';

                backgroundRec.onstart = () => {
                    isBackgroundStarting.current = false;
                };

                backgroundRec.onresult = (event: any) => {
                    const result = event.results[event.results.length - 1];
                    const text = result[0].transcript.toLowerCase();
                    const wakeWords = ["hey chitti", "hey gritty", "hey city", "hey kitty", "hey pretty", "hey chetti", "chitti", "city"];
                    if (wakeWords.some(word => text.includes(word))) {
                        console.log("[VoiceBot] Wake word detected!");
                        stopBackground();
                        setIsActive(true);
                        setIsDismissed(false);
                        // Significant delay to allow background listener to fully release microphone
                        setTimeout(() => startMain(), 600);
                    }
                };

                backgroundRec.onerror = (event: any) => {
                    isBackgroundStarting.current = false;
                    // Silent on aborted/no-speech
                    if (event.error !== 'no-speech' && event.error !== 'aborted') {
                        console.warn("[VoiceBot] Background recognition error:", event.error);
                    }
                };

                backgroundRec.onend = () => {
                    isBackgroundStarting.current = false;
                    // Auto-restart handled by useEffect
                };
                backgroundRecognitionRef.current = backgroundRec;
            }
        }

        return () => {
            if (synthRef.current) synthRef.current.cancel();
            stopMain();
            stopBackground();
        };
    }, [currentUser]);

    // --- Lifecycle Manager ---

    useEffect(() => {
        const timer = setTimeout(() => {
            if (botState === 'idle' && isWakeWordEnabled && !isDismissed && !isActive) {
                startBackground();
            } else {
                stopBackground();
            }
        }, 1200); // Coordinated cooldown between sessions
        return () => clearTimeout(timer);
    }, [botState, isWakeWordEnabled, isDismissed, isActive]);

    // --- LLM Interaction ---

    useEffect(() => {
        if (botState === 'thinking') {
            const processTranscript = async () => {
                const textToProcess = transcript.trim();
                if (textToProcess !== '') {
                    setDisplayText("Thinking...");
                    try {
                        const context = { currentView };
                        const response = await getChatAssistantResponse(textToProcess, context);
                        setAiResponse(response);
                        setBotState('speaking');
                    } catch (error) {
                        setDisplayText("Sorry, my neural net glitched. Try again!");
                        setBotState('idle');
                    }
                } else {
                    setBotState('idle');
                    setDisplayText("I'm here when you're ready!");
                }
            };
            processTranscript();
        }
    }, [botState, transcript, currentView]);

    // --- Speech Synthesis ---

    const speak = (text: string) => {
        if (!synthRef.current) return;
        synthRef.current.cancel();

        let cleanText = text.replace(/[*#`_~]/g, '');
        if (cleanText.length > 300) {
            cleanText = cleanText.substring(0, 300) + "...";
        }

        const utterance = new SpeechSynthesisUtterance(cleanText);
        const voices = synthRef.current.getVoices();
        let preferredVoice = voices.find(v => v.lang === 'en-IN' || v.lang === 'hi-IN' || v.name.toLowerCase().includes('india'))
            || voices.find(v => v.name.includes('Google UK English Male') || v.lang === 'en-US');

        if (voiceBotSettings?.voiceURI) {
            const configuredVoice = voices.find(v => v.voiceURI === voiceBotSettings.voiceURI);
            if (configuredVoice) preferredVoice = configuredVoice;
        }
        if (preferredVoice) utterance.voice = preferredVoice;

        utterance.rate = voiceBotSettings?.rate ?? 1.05;
        utterance.pitch = voiceBotSettings?.pitch ?? 1.1;

        utterance.onstart = () => {
            setBotState('speaking');
            setDisplayText("Speaking...");
        };

        utterance.onend = () => {
            setBotState('idle');
            setDisplayText("How else can I help?");

            if (aiResponseRef.current && aiResponseRef.current.includes('[AUTO_CONTINUE]')) {
                setTimeout(() => {
                    if (isActive && !isDismissed) {
                        setTranscript("auto_continue");
                        setBotState('thinking');
                        setDisplayText("Continuing...");
                    }
                }, 1000);
            } else {
                setTimeout(() => {
                    if (isActive && !isDismissed && synthRef.current && !synthRef.current.speaking) {
                        console.log("[VoiceBot] Resuming active listener...");
                        startMain();
                    }
                }, 800);
            }
        };

        utterance.onerror = () => setBotState('idle');
        utteranceRef.current = utterance;
        synthRef.current.speak(utterance);
    };

    // Trigger speak and navigation when aiResponse changes
    useEffect(() => {
        if (botState === 'speaking' && aiResponse) {
            const navMatch = aiResponse.match(/\[?NAVIGATE:\s*([a-zA-Z0-9_-]+)\s*\]?/i);
            if (navMatch && navMatch[1]) {
                const targetView = navMatch[1].trim().toLowerCase();
                const navigationMap: Record<string, AppView> = {
                    'dashboard': 'dashboard', 'home': 'dashboard', 'agents': 'agents', 'assets': 'assetManagement',
                    'inventory': 'assetManagement', 'patching': 'patchManagement', 'patches': 'patchManagement',
                    'vulnerabilities': 'vulnerabilityManagement', 'vulns': 'vulnerabilityManagement',
                    'updates': 'softwareUpdates', 'cloud': 'cloudSecurity', 'security': 'security',
                    'compliance': 'compliance', 'governance': 'aiGovernance', 'billing': 'finops',
                    'finops': 'finops', 'audit': 'auditLog', 'logs': 'auditLog', 'settings': 'settings',
                    'tenants': 'tenantManagement', 'users': 'userManagement', 'roles': 'roleManagement',
                    'keys': 'apiKeys', 'integrations': 'integrations', 'playbooks': 'playbooks',
                    'threats': 'threatIntelligence', 'intel': 'threatIntelligence', 'insights': 'proactiveInsights',
                    'tracing': 'distributedTracing', 'data': 'dataSecurity', 'attack': 'attackPath',
                    'catalog': 'serviceCatalog', 'dora': 'doraMetrics', 'chaos': 'chaosEngineering',
                    'network': 'networkObservability', 'pricing': 'servicePricing', 'tasks': 'tasks',
                    'deployment': 'softwareDeployment', 'webhooks': 'webhooks', 'digital': 'digitalTwin',
                    'simulation': 'securitySimulation', 'health': 'systemHealth', 'payments': 'paymentSettings',
                    'invoices': 'invoices', 'persistence': 'persistence', 'security-audit': 'securityAudit',
                    'bi': 'advancedBi', 'cxo': 'cxo', 'cxo-insights': 'cxo', 'executive': 'cxo',
                    'ceo': 'cxo', 'warehouse': 'dataWarehouse', 'streaming': 'streaming',
                    'data-governance': 'dataGovernance', 'mlops': 'mlops', 'auto': 'automl',
                    'xai': 'xai', 'testing': 'abTesting', 'explorer': 'logExplorer',
                    'hunting': 'threatHunting', 'profile': 'profile', 'devsecops': 'devsecops',
                    'sbom': 'sbom', 'hub': 'developer_hub', 'impact': 'incidentImpact',
                    'siem': 'siem', 'ueba': 'ueba'
                };

                const target = targetView.toLowerCase();
                const finalView = navigationMap[target] || (target as AppView);

                if (finalView) {
                    setTimeout(() => { setCurrentView(finalView); }, 500);
                }
            }

            let speechText = aiResponse.replace(/\[?NAVIGATE:[\w-]+\]?/gi, '');
            speechText = speechText.replace(/\[?AUTO_CONTINUE\]?/gi, '').trim();
            speak(speechText);
        }
    }, [botState, aiResponse]);

    // --- UI Controls ---

    const toggleListening = () => {
        if (!isActive) {
            setIsActive(true);
            setIsDismissed(false);
            if (synthRef.current && synthRef.current.getVoices().length === 0) {
                synthRef.current.speak(new SpeechSynthesisUtterance(''));
                synthRef.current.cancel();
            }
        }

        if (botState === 'idle') {
            if (!recognitionRef.current) {
                setDisplayText("Speech recognition not supported.");
                return;
            }
            if (synthRef.current) synthRef.current.cancel();
            setTranscript('');
            setAiResponse('');
            
            // Critical transition: Stop background, wait for release, then start main
            stopBackground();
            setTimeout(() => startMain(), 400);
        } else if (botState === 'listening') {
            stopMain();
        } else if (botState === 'speaking') {
            if (synthRef.current) synthRef.current.cancel();
            setBotState('idle');
            setDisplayText("Okay, I'll be quiet.");
        }
    };

    const closeBot = () => {
        setIsActive(false);
        setIsDismissed(true);
        if (synthRef.current) synthRef.current.cancel();
        stopMain();
        stopBackground();
        setBotState('idle');
    };

    // Simulation hook for browser tests
    useEffect(() => {
        (window as any).simulateSpeech = (text: string) => {
            setIsActive(true);
            setIsDismissed(false);
            setTranscript(text);
            setBotState('thinking');
            setAiResponse("Hmm, let me process that... [NAVIGATE:dashboard]");
        };
    }, []);

    // --- UI Rendering ---

    if (isDismissed && !isActive) return null;
    if (voiceBotSettings && voiceBotSettings.enabled === false) return null;

    let ringColor = 'border-primary-400';
    let ringPingColor = 'border-indigo-400';
    let icon = <MicIcon size={24} className="text-white" />;

    if (botState === 'listening') {
        ringColor = 'border-green-400';
        ringPingColor = 'border-green-300';
        icon = <MicIcon size={24} className="text-white select-none animate-pulse" />;
    } else if (botState === 'thinking') {
        ringColor = 'border-yellow-400';
        ringPingColor = 'transparent';
        icon = <LoaderIcon size={24} className="text-white animate-spin" />;
    } else if (botState === 'speaking') {
        ringColor = 'border-blue-400';
        ringPingColor = 'border-cyan-400';
        icon = <Volume2Icon size={24} className="text-white scale-110" />;
    }

    const VoiceWave = () => (
        <div className="flex items-center justify-center space-x-1 h-8 px-2">
            {[1, 2, 3, 4, 5].map((i) => (
                <div
                    key={i}
                    className="w-1 bg-gradient-to-t from-primary-400 to-cyan-300 rounded-full animate-voice-wave opacity-80"
                    style={{
                        height: '100%',
                        animationDelay: `${i * 0.1}s`,
                        animationDuration: `${0.5 + Math.random()}s`
                    }}
                ></div>
            ))}
        </div>
    );

    return (
        <div className="fixed bottom-24 right-6 z-[60] flex flex-col items-end pointer-events-none">
            <style dangerouslySetInnerHTML={{
                __html: `
                @keyframes voice-wave { 0%, 100% { transform: scaleY(0.3); } 50% { transform: scaleY(1); } }
                .animate-voice-wave { animation: voice-wave 0.6s ease-in-out infinite; }
            `}} />

            {isActive && (botState !== 'idle' || aiResponse || transcript) && (
                <div className="bg-white dark:bg-gray-800 rounded-2xl rounded-br-sm shadow-2xl p-4 mb-4 max-w-sm border border-primary-500/30 transform transition-all duration-300 animate-in fade-in slide-in-from-bottom-4 pointer-events-auto relative overflow-hidden">
                    <div className={`absolute top-0 left-0 w-full h-1 bg-gradient-to-r ${botState === 'listening' ? 'from-green-400 to-green-600' :
                        botState === 'thinking' ? 'from-yellow-400 to-orange-500' :
                            botState === 'speaking' ? 'from-blue-400 to-cyan-500' :
                                'from-primary-500 to-indigo-500'
                        }`}></div>

                    <div className="text-xs text-primary-500 dark:text-primary-400 font-bold uppercase tracking-wider mb-2 flex items-center">
                        {botState === 'listening' ? "🎤 Listening..." :
                            botState === 'thinking' ? "🧠 Thinking..." :
                                botState === 'speaking' ? "🗣️ Chitti:" : "Chitti"}
                    </div>

                    <div className="text-sm text-gray-700 dark:text-gray-200 leading-relaxed font-medium max-h-48 overflow-y-auto pr-2 custom-scrollbar">
                        {botState === 'speaking' || (botState === 'idle' && aiResponse) ? (
                            <div className="prose prose-sm dark:prose-invert max-w-none prose-p:my-1 prose-ul:my-1">
                                {aiResponse.replace(/\[?NAVIGATE:[\w-]+\]?/gi, '') || displayText}
                                {botState === 'speaking' && <VoiceWave />}
                            </div>
                        ) : (
                            <div className="flex flex-col space-y-2">
                                <span className={botState === 'listening' ? 'mb-2 italic text-gray-500' : ''}>
                                    "{transcript || displayText}"
                                </span>
                                {botState === 'listening' && <VoiceWave />}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {!isActive && !isDismissed && (
                <div className="bg-white dark:bg-gray-800 rounded-2xl rounded-br-sm shadow-lg p-3 mb-4 border border-gray-200 dark:border-gray-700 animate-bounce pointer-events-auto cursor-pointer" onClick={toggleListening}>
                    <p className="text-sm text-gray-700 dark:text-gray-300">
                        {displayText}
                    </p>
                </div>
            )}

            <button
                onClick={toggleListening}
                className={`relative group flex items-center justify-center w-16 h-16 rounded-full shadow-2xl shadow-primary-500/40 pointer-events-auto transition-all duration-500 ease-out
                    ${botState !== 'idle' ? 'bg-gradient-to-br from-indigo-600 via-primary-600 to-cyan-500 scale-110 rotate-3' : 'bg-gray-900 dark:bg-gray-800 hover:bg-primary-600'}
                `}
                style={{ boxShadow: botState !== 'idle' ? '0 0 30px rgba(99, 102, 241, 0.6)' : undefined }}
                title={botState === 'idle' ? 'Say "Hey Chitti"...' : "Click to stop"}
            >
                {botState !== 'idle' && (
                    <>
                        <div className={`absolute inset-0 rounded-full border-2 ${ringColor} animate-ping opacity-75`}></div>
                        {botState !== 'thinking' && (
                            <div className={`absolute inset-0 rounded-full border-2 ${ringPingColor} animate-ping opacity-50 animation-delay-200`}></div>
                        )}
                    </>
                )}
                {icon}
                {(botState === 'idle') && (
                    <div
                        onClick={(e) => { e.stopPropagation(); closeBot(); }}
                        className="absolute -top-1 -right-1 bg-red-500 text-white rounded-full p-0.5 hover:bg-red-600 opacity-0 group-hover:opacity-100 transition-opacity z-10"
                    >
                        <XIcon size={12} />
                    </div>
                )}
            </button>
        </div>
    );
};
