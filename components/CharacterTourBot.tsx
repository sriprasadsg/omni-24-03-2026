import React, { useState, useEffect, useRef } from 'react';
import { MascotCharacter, BotState, CharacterType } from './MascotCharacter';
import { XIcon, PlayIcon, PauseIcon } from './icons';
import { AppView } from '../types';

interface TourStep {
    text: string;
    targetView?: AppView;
    highlightSelector?: string;
    delayAfter?: number;
}

interface CharacterTourBotProps {
    currentUser: any;
    currentView: AppView;
    setCurrentView: (view: AppView) => void;
}

export const CharacterTourBot: React.FC<CharacterTourBotProps> = ({ currentUser, currentView, setCurrentView }) => {
    const [isActive, setIsActive] = useState(false);
    const [characterType, setCharacterType] = useState<CharacterType>('genesis');
    const [botState, setBotState] = useState<BotState>('idle');
    const [currentStep, setCurrentStep] = useState(-1); // -1 = character selection

    const synthRef = useRef<SpeechSynthesis | null>(null);
    const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

    // Elaborate tour script explaining features in depth
    const getTourScript = (guideName: string): TourStep[] => [
        {
            text: `Welcome to the Omni-Agent AI Platform, the world's most advanced autonomous enterprise framework. I am ${guideName}, your personal AI guide. Today, I will take you on a comprehensive journey through our platform's capabilities, demonstrating how we unify security, compliance, and operations into a single pane of glass.`,
            targetView: 'dashboard',
            delayAfter: 2000
        },
        {
            text: `This is your main Command Center Dashboard. From here, you have a bird's-eye view of your entire infrastructure. You can instantly monitor active agents, system health, security cases, and proactive insights without having to switch between different tools or environments.`,
            targetView: 'dashboard',
            delayAfter: 2000
        },
        {
            text: `Let's navigate to Asset Management. The platform automatically discovers and categorizes every server, laptop, virtual machine, and endpoint in your network in real-time. This dynamic inventory ensures you never have unknown devices running on your infrastructure, minimizing your attack surface.`,
            targetView: 'assetManagement',
            highlightSelector: '[title="Assets"]',
            delayAfter: 2000
        },
        {
            text: `Security is the core of our platform. Here in the Security Operations Center, our AI models analyze millions of events per second to detect advanced persistent threats, malicious behaviors, and unauthorized access attempts. We instantly correlate this data to give your team actionable cases rather than overwhelming them with noisy alerts.`,
            targetView: 'security',
            highlightSelector: '[title="Security"]',
            delayAfter: 2500
        },
        {
            text: `Managing software supply chain risk has never been easier. In the Dev Sec Ops dashboard, we automatically ingest and analyze Software Bill of Materials documents. The system scans all components against global vulnerability databases to ensure your custom applications are secure before they even reach production.`,
            targetView: 'devsecops',
            highlightSelector: '[title="DevSecOps"]',
            delayAfter: 3000
        },
        {
            text: `Meeting regulatory requirements is a breeze with our Compliance Module. We map your actual infrastructure state against frameworks like SOC 2, HIPAA, and ISO 27001 continuously. This means you are always audit-ready, drastically reducing the time and cost associated with manual compliance checks.`,
            targetView: 'compliance',
            highlightSelector: '[title="Compliance"]',
            delayAfter: 2500
        },
        {
            text: `As your organization adopts more Artificial Intelligence, our AI Governance dashboard provides complete visibility. You can monitor all internal AI models and large language models, ensuring ethical use, tracking fairness metrics, and keeping AI systems aligned with your corporate policies.`,
            targetView: 'aiGovernance',
            highlightSelector: '[title="AI Governance"]',
            delayAfter: 2500
        },
        {
            text: `Cloud spending can quickly spiral out of control. Our Fin-Ops billing features analyze your resource utilization across AWS, Azure, and GCP to recommend cost-saving opportunities, ensuring you never pay for idle capacity or over-provisioned infrastructure.`,
            targetView: 'finops',
            delayAfter: 2500
        },
        {
            text: `Finally, our Sustainability tracking helps you achieve your corporate net-zero goals. By tracking the energy consumption of your specific data centers and cloud nodes, we provide accurate carbon footprint reporting and identify workloads that can be shifted to greener energy regions.`,
            targetView: 'sustainability',
            delayAfter: 2500
        },
        {
            text: `That concludes our detailed architectural tour. The platform offers far more capabilities, including chaos engineering, network observability, and distributed tracing. Feel free to explore independently, or ask me specific questions at any time. Returning you to the main dashboard.`,
            targetView: 'dashboard',
            delayAfter: 1500
        }
    ];

    const guideNameMap = {
        genesis: 'G.E.N.E.S.I.S',
        athena: 'Athena',
        nexus: 'Nexus Core',
        heartbot: 'Heart Bot',
        nova: 'Nova'
    };
    
    const script = getTourScript(guideNameMap[characterType]);

    useEffect(() => {
        if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
            synthRef.current = window.speechSynthesis;
        }

        const handleStartTour = () => {
            setIsActive(true);
            setCurrentStep(-1); // Open Character Selection
        };

        window.addEventListener('start-genesis-tour', handleStartTour);
        return () => window.removeEventListener('start-genesis-tour', handleStartTour);
    }, []);

    useEffect(() => {
        return () => {
            if (synthRef.current) {
                synthRef.current.cancel();
            }
        };
    }, []);

    function playStep(stepIndex: number) {
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

        document.querySelectorAll('.tour-highlight').forEach(el => el.classList.remove('tour-highlight'));

        if (step.highlightSelector) {
            setTimeout(() => {
                const el = document.querySelector(step.highlightSelector);
                if (el) {
                    el.classList.add('tour-highlight');
                    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            }, 300);
        }

        // 2. Speech Synthesis
        synthRef.current.cancel();

        const utterance = new SpeechSynthesisUtterance(step.text);
        const voices = synthRef.current.getVoices();
        
        // Try to assign a matching personality voice based on character
        let preferredVoice;
        if (characterType === 'athena') {
            preferredVoice = voices.find(v => v.name.includes('Samantha') || v.name.includes('Victoria') || (v.lang.includes('en') && v.name.includes('Female')));
        } else if (characterType === 'nexus') {
            // Nexus sounds deep/robotic/neutral
            preferredVoice = voices.find(v => v.name.includes('Daniel') || v.name.includes('Alex') || v.name.includes('Male Head'));
        } else if (characterType === 'heartbot') {
            // Heart Bot sounds sweet and female
            preferredVoice = voices.find(v => v.name.includes('Samantha') || v.name.includes('Google UK English Female') || (v.lang.includes('en') && v.name.includes('Female')));
        } else if (characterType === 'nova') {
            // Nova is energetic and cheerful
            preferredVoice = voices.find(v => v.name.includes('Karen') || v.name.includes('Victoria') || v.lang.includes('en-AU') || (v.lang.includes('en') && v.name.includes('Female')));
        } else {
            // Genesis (Indian/Friendly)
            preferredVoice = voices.find(v => v.lang === 'en-IN' || v.lang === 'hi-IN' || v.name.toLowerCase().includes('india'))
                || voices.find(v => v.name.includes('Google UK English Male') || v.lang === 'en-US');
        }
            
        if (preferredVoice) utterance.voice = preferredVoice;

        // Slowed down rate for elaborate explanations
        utterance.rate = 0.90; 
        utterance.pitch = characterType === 'athena' ? 1.2 : characterType === 'nexus' ? 0.8 : characterType === 'heartbot' ? 1.3 : characterType === 'nova' ? 1.25 : 1.1;

        utterance.onstart = () => setBotState('speaking');

        utterance.onend = () => {
            setBotState('idle');
            setTimeout(() => {
                if (isActive) {
                    setCurrentStep(prev => prev + 1);
                }
            }, step.delayAfter || 1000);
        };

        utterance.onerror = (e) => {
            console.error('Speech synthesis error:', e);
            setBotState('idle');
            setTimeout(() => {
                if (isActive) setCurrentStep(prev => prev + 1);
            }, 3000);
        };

        utteranceRef.current = utterance;
        synthRef.current.speak(utterance);
    }

    useEffect(() => {
        if (isActive && currentStep >= 0 && currentStep < script.length) {
            playStep(currentStep);
        } else if (isActive && currentStep >= script.length) {
            endTour();
        }
    }, [currentStep, isActive, currentView]); 

    function selectCharacterAndStart(type: CharacterType) {
        setCharacterType(type);
        setBotState('thinking');
        
        if (synthRef.current && synthRef.current.getVoices().length === 0) {
            synthRef.current.speak(new SpeechSynthesisUtterance(''));
            synthRef.current.cancel();
        }

        // Slight delay before starting to show "thinking" transition
        setTimeout(() => {
            setCurrentStep(0);
        }, 1000);
    }

    function pauseResumeTour() {
        if (!synthRef.current) return;
        if (synthRef.current.paused) {
            synthRef.current.resume();
            setBotState('speaking');
        } else if (synthRef.current.speaking) {
            synthRef.current.pause();
            setBotState('idle'); 
        }
    }

    function endTour() {
        setIsActive(false);
        setBotState('idle');
        setCurrentStep(-1);
        if (synthRef.current) synthRef.current.cancel();
        document.querySelectorAll('.tour-highlight').forEach(el => el.classList.remove('tour-highlight'));
    }

    if (!isActive) return null;

    // Phase 1: Character Selection Screen
    if (currentStep === -1) {
        return (
            <div className="fixed inset-0 z-[100] flex items-center justify-center bg-gray-900/60 backdrop-blur-sm shadow-xl p-4 fade-in">
                <div className="bg-white dark:bg-gray-800 rounded-2xl p-8 max-w-3xl w-full border border-gray-200 dark:border-gray-700 shadow-2xl relative overflow-hidden">
                    <div className="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-blue-500 via-purple-500 to-orange-500"></div>
                    
                    <button onClick={endTour} className="absolute top-4 right-4 text-gray-400 hover:text-red-500 transition-colors">
                        <XIcon size={24} />
                    </button>
                    
                    <h2 className="text-3xl font-bold text-center text-gray-900 dark:text-white mb-2">Choose Your AI Guide</h2>
                    <p className="text-center text-gray-500 dark:text-gray-400 mb-8 max-w-xl mx-auto">
                        Select a persona to lead you through an interactive demonstration of the Omni-Agent AI Platform.
                    </p>
                    
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
                        {/* Genesis */}
                        <div 
                            onClick={() => selectCharacterAndStart('genesis')}
                            className="flex flex-col items-center justify-center p-4 border-2 border-gray-100 dark:border-gray-700 rounded-xl hover:border-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/20 cursor-pointer transition-all hover:scale-105 group"
                        >
                            <div className="w-24 h-24 mb-4 relative z-0">
                                <MascotCharacter botState="idle" type="genesis" className="w-full h-full pointer-events-none" />
                            </div>
                            <h3 className="text-xl font-bold text-gray-900 dark:text-white group-hover:text-blue-600 dark:group-hover:text-blue-400">G.E.N.E.S.I.S</h3>
                            <p className="text-sm text-center text-gray-500 dark:text-gray-400 mt-2">
                                Friendly, enthusiastic, and highly analytical. Perfect for a standard operational overview.
                            </p>
                        </div>
                        
                        {/* Athena */}
                        <div 
                            onClick={() => selectCharacterAndStart('athena')}
                            className="flex flex-col items-center justify-center p-4 border-2 border-gray-100 dark:border-gray-700 rounded-xl hover:border-purple-500 hover:bg-purple-50 dark:hover:bg-purple-900/20 cursor-pointer transition-all hover:scale-105 group"
                        >
                            <div className="w-24 h-24 mb-4 relative z-0">
                                <MascotCharacter botState="idle" type="athena" className="w-full h-full pointer-events-none" />
                            </div>
                            <h3 className="text-xl font-bold text-gray-900 dark:text-white group-hover:text-purple-600 dark:group-hover:text-purple-400">Athena</h3>
                            <p className="text-sm text-center text-gray-500 dark:text-gray-400 mt-2">
                                Sleek, logical, and focused on strategy. An executive-level guide for governance and security.
                            </p>
                        </div>

                        {/* Nexus */}
                        <div 
                            onClick={() => selectCharacterAndStart('nexus')}
                            className="flex flex-col items-center justify-center p-4 border-2 border-gray-100 dark:border-gray-700 rounded-xl hover:border-orange-500 hover:bg-orange-50 dark:hover:bg-orange-900/20 cursor-pointer transition-all hover:scale-105 group"
                        >
                            <div className="w-24 h-24 mb-4 relative z-0">
                                <MascotCharacter botState="idle" type="nexus" className="w-full h-full pointer-events-none" />
                            </div>
                            <h3 className="text-xl font-bold text-gray-900 dark:text-white group-hover:text-orange-600 dark:group-hover:text-orange-400">Nexus Core</h3>
                            <p className="text-sm text-center text-gray-500 dark:text-gray-400 mt-2">
                                Deep, technical, and data-driven. Ideal for deep-dives into DevSecOps and backend capabilities.
                            </p>
                        </div>

                        {/* Heart Bot */}
                        <div 
                            onClick={() => selectCharacterAndStart('heartbot')}
                            className="flex flex-col items-center justify-center p-4 border-2 border-gray-100 dark:border-gray-700 rounded-xl hover:border-pink-500 hover:bg-pink-50 dark:hover:bg-pink-900/20 cursor-pointer transition-all hover:scale-105 group"
                        >
                            <div className="w-24 h-24 mb-4 relative z-0">
                                <MascotCharacter botState="idle" type="heartbot" className="w-full h-full pointer-events-none" />
                            </div>
                            <h3 className="text-xl font-bold text-gray-900 dark:text-white group-hover:text-pink-600 dark:group-hover:text-pink-400">Heart Bot</h3>
                            <p className="text-sm text-center text-gray-500 dark:text-gray-400 mt-2">
                                Cute, friendly, and affectionate. A caring guide spreading love across the platform.
                            </p>
                        </div>
                        
                        {/* Nova */}
                        <div 
                            onClick={() => selectCharacterAndStart('nova')}
                            className="flex flex-col items-center justify-center p-4 border-2 border-gray-100 dark:border-gray-700 rounded-xl hover:border-teal-500 hover:bg-teal-50 dark:hover:bg-teal-900/20 cursor-pointer transition-all hover:scale-105 group"
                        >
                            <div className="w-24 h-24 mb-4 relative z-0">
                                <MascotCharacter botState="idle" type="nova" className="w-full h-full pointer-events-none" />
                            </div>
                            <h3 className="text-xl font-bold text-gray-900 dark:text-white group-hover:text-teal-600 dark:group-hover:text-teal-400">Nova</h3>
                            <p className="text-sm text-center text-gray-500 dark:text-gray-400 mt-2">
                                Energetic, expressive, and interactive. An animated guide who projects holograms and loves data!
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    // Phase 2: Active Tour
    return (
        <div className="fixed bottom-24 right-28 z-50 flex items-end space-x-4 pointer-events-none fade-in">
            {/* Mascot Avatar */}
            <MascotCharacter botState={botState} type={characterType} onClick={pauseResumeTour} className="pointer-events-auto" />

            {/* Speech Bubble */}
            <div className={`bg-white dark:bg-gray-800 rounded-2xl rounded-bl-none shadow-2xl p-4 mb-4 mt-8 max-w-sm border ${characterType === 'athena' ? 'border-purple-500/30' : characterType === 'nexus' ? 'border-orange-500/30' : 'border-blue-500/30'} transform transition-all duration-300 animate-in fade-in slide-in-from-left-4 pointer-events-auto relative overflow-hidden`}>
                <div className={`absolute top-0 left-0 w-full h-1 bg-gradient-to-r ${characterType === 'athena' ? 'from-pink-500 to-purple-500' : characterType === 'nexus' ? 'from-amber-500 to-orange-500' : 'from-blue-500 to-cyan-500'}`}></div>
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
                            className="p-1.5 text-gray-500 hover:text-blue-500 hover:bg-blue-50 dark:hover:bg-gray-700 rounded-md transition-colors"
                            title={synthRef.current?.paused ? "Resume Tour" : "Pause Tour"}
                        >
                            {synthRef.current?.paused ? <PlayIcon size={14} /> : <PauseIcon size={14} />}
                        </button>
                        <button
                            onClick={endTour}
                            className="p-1.5 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-md transition-colors"
                            title="End Tour"
                        >
                            <XIcon size={14} />
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};
