import React from 'react';

export type BotState = 'idle' | 'listening' | 'thinking' | 'speaking';
export type CharacterType = 'genesis' | 'athena' | 'nexus' | 'heartbot' | 'nova';

interface MascotCharacterProps {
    botState: BotState;
    type: CharacterType;
    className?: string;
    onClick?: () => void;
}

export const MascotCharacter: React.FC<MascotCharacterProps> = ({ botState, type, className = '', onClick }) => {
    // Determine styles based on bot state and character type
    
    // Default Genesis Colors (Blue/Cyan)
    let ringColor = 'border-primary-400';
    let ringPingColor = 'border-indigo-400';
    
    if (type === 'athena') {
        ringColor = 'border-purple-400';
        ringPingColor = 'border-pink-400';
    } else if (type === 'nexus') {
        ringColor = 'border-orange-400';
        ringPingColor = 'border-amber-400';
    } else if (type === 'heartbot') {
        ringColor = 'border-pink-400';
        ringPingColor = 'border-rose-400';
    } else if (type === 'nova') {
        ringColor = 'border-teal-400';
        ringPingColor = 'border-cyan-400';
    }

    if (botState === 'listening') {
        ringColor = 'border-green-400';
        ringPingColor = 'border-green-300';
    } else if (botState === 'thinking') {
        ringColor = 'border-yellow-400';
        ringPingColor = 'transparent';
    } else if (botState === 'speaking') {
        if (type === 'genesis') { ringColor = 'border-blue-400'; ringPingColor = 'border-cyan-400'; }
        if (type === 'athena') { ringColor = 'border-pink-500'; ringPingColor = 'border-purple-500'; }
        if (type === 'nexus') { ringColor = 'border-amber-500'; ringPingColor = 'border-orange-500'; }
    }

    // Helper to render the specific SVG based on selected character "type"
    const renderCharacterSVG = () => {
        if (type === 'genesis') {
            // GENESIS (Original friendly robot)
            return (
                <svg viewBox="0 0 100 100" className="w-full h-full drop-shadow-2xl">
                    <rect x="15" y="20" width="70" height="60" rx="20" className={`fill-gray-900 stroke-2 ${botState !== 'idle' ? 'stroke-indigo-400' : 'stroke-gray-600'}`} />
                    <rect x="25" y="30" width="50" height="40" rx="10" className="fill-gray-800" />
                    
                    <line x1="20" y1="40" x2="8" y2="35" className="stroke-4 stroke-gray-600" strokeWidth="4" strokeLinecap="round" />
                    <circle cx="8" cy="35" r="4" className={`${botState !== 'idle' ? 'fill-cyan-400 shadow-glow' : 'fill-gray-500'}`} />
                    
                    <line x1="80" y1="40" x2="92" y2="35" className="stroke-4 stroke-gray-600" strokeWidth="4" strokeLinecap="round" />
                    <circle cx="92" cy="35" r="4" className={`${botState !== 'idle' ? 'fill-cyan-400 shadow-glow' : 'fill-gray-500'}`} />
                    
                    <g className="bot-blink">
                        <ellipse cx="38" cy="45" rx="6" ry="8" className={botState === 'thinking' ? "fill-yellow-400" : botState === 'speaking' ? "fill-cyan-400" : "fill-blue-400"} />
                        <ellipse cx="62" cy="45" rx="6" ry="8" className={botState === 'thinking' ? "fill-yellow-400" : botState === 'speaking' ? "fill-cyan-400" : "fill-blue-400"} />
                        <circle cx="36" cy="42" r="2" fill="white" opacity="0.8" />
                        <circle cx="60" cy="42" r="2" fill="white" opacity="0.8" />
                    </g>

                    {botState === 'speaking' ? (
                        <ellipse cx="50" cy="62" rx="6" ry="2" className="fill-cyan-400 bot-mouth-speak" />
                    ) : botState === 'thinking' ? (
                        <line x1="45" y1="62" x2="55" y2="62" stroke="#facc15" strokeWidth="2" strokeLinecap="round" />
                    ) : botState === 'listening' ? (
                        <circle cx="50" cy="62" r="4" className="fill-green-400 animate-pulse" />
                    ) : (
                        <path d="M 40 60 Q 50 66 60 60" fill="none" stroke="#60a5fa" strokeWidth="3" strokeLinecap="round" />
                    )}
                </svg>
            );
        } else if (type === 'athena') {
            // ATHENA (Futuristic spherical "Eye" AI)
            return (
                <svg viewBox="0 0 100 100" className="w-full h-full drop-shadow-2xl">
                    <circle cx="50" cy="50" r="40" className={`fill-gray-900 stroke-4 ${botState !== 'idle' ? 'stroke-purple-500' : 'stroke-gray-600'}`} strokeWidth="4" />
                    <circle cx="50" cy="50" r="30" className="fill-gray-800" />
                    
                    {/* Inner glowing Iris */}
                    <circle cx="50" cy="50" r={botState === 'speaking' ? 22 : 18} className={`transition-all duration-300 ${botState === 'thinking' ? "fill-yellow-500" : botState === 'speaking' ? "fill-pink-500 bot-iris-pulse" : "fill-purple-500"}`} />
                    <circle cx="50" cy="50" r={botState === 'speaking' ? 12 : 10} className="fill-white opacity-90" />
                    
                    {/* Tech rings */}
                    <path d="M 20 50 A 30 30 0 0 1 80 50" fill="none" stroke={botState !== 'idle' ? "#f472b6" : "#4b5563"} strokeWidth="2" strokeDasharray="5,5" className={botState === 'speaking' ? "animate-spin-slow" : ""} style={{ transformOrigin: '50% 50%' }} />
                    <path d="M 80 50 A 30 30 0 0 1 20 50" fill="none" stroke={botState !== 'idle' ? "#c084fc" : "#4b5563"} strokeWidth="2" strokeDasharray="10,5" className={botState === 'speaking' ? "animate-spin-reverse-slow" : ""} style={{ transformOrigin: '50% 50%' }} />
                </svg>
            );
        } else if (type === 'nexus') {
            // NEXUS (Holographic floating pyramid / energetic core)
            return (
                <svg viewBox="0 0 100 100" className="w-full h-full drop-shadow-2xl">
                    {/* Floating Base */}
                    <ellipse cx="50" cy="85" rx="30" ry="10" className="fill-gray-900 opacity-50" />
                    
                    {/* Pyramid Outer */}
                    <polygon points="50,15 20,70 80,70" className={`fill-gray-800 stroke-2 ${botState !== 'idle' ? 'stroke-amber-500' : 'stroke-gray-600'} transition-colors`} />
                    
                    {/* Pyramid Inner Core */}
                    <polygon points="50,30 35,65 65,65" className={`transition-all duration-300 ${botState === 'thinking' ? "fill-yellow-400" : botState === 'speaking' ? "fill-orange-400 bot-core-pulse" : "fill-amber-600"}`} />
                    
                    {/* Energy lines */}
                    {botState === 'speaking' && (
                        <>
                            <line x1="50" y1="15" x2="50" y2="5" className="stroke-orange-400 stroke-2 animate-ping" />
                            <line x1="20" y1="70" x2="10" y2="75" className="stroke-orange-400 stroke-2 animate-ping" />
                            <line x1="80" y1="70" x2="90" y2="75" className="stroke-orange-400 stroke-2 animate-ping" />
                        </>
                    )}
                </svg>
            );
        } else if (type === 'heartbot') {
            // HEARTBOT (Cute 3D-like Robot SVG built from scratch)
            return (
                <svg viewBox="0 0 100 100" className="w-full h-full drop-shadow-2xl overflow-visible">
                    <defs>
                        <linearGradient id="hbBody" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" stopColor="#ffffff"/>
                            <stop offset="100%" stopColor="#cbd5e1"/>
                        </linearGradient>
                        <linearGradient id="hbScreen" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" stopColor="#1e293b"/>
                            <stop offset="100%" stopColor="#0f172a"/>
                        </linearGradient>
                        <linearGradient id="hbEar" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" stopColor="#fca5a5"/>
                            <stop offset="100%" stopColor="#ef4444"/>
                        </linearGradient>
                    </defs>

                    {/* Floating Hearts if Listening or Happy */}
                    {botState === 'listening' && (
                        <g className="opacity-0 heart-anim-1">
                            <path d="M50 15 A3 3 0 0 0 44 15 A3 3 0 0 0 50 21 A3 3 0 0 0 56 15 A3 3 0 0 0 50 15 Z" fill="#f472b6" />
                        </g>
                    )}
                    {botState === 'speaking' && (
                        <>
                            <g className="opacity-0 heart-anim-1" transform="translate(-10, 0)">
                                <path d="M50 15 A2 2 0 0 0 46 15 A2 2 0 0 0 50 19 A2 2 0 0 0 54 15 A2 2 0 0 0 50 15 Z" fill="#fb7185" />
                            </g>
                            <g className="opacity-0 heart-anim-2" transform="translate(15, -5)">
                                <path d="M50 15 A3 3 0 0 0 44 15 A3 3 0 0 0 50 21 A3 3 0 0 0 56 15 A3 3 0 0 0 50 15 Z" fill="#f472b6" />
                            </g>
                            <g className="opacity-0 heart-anim-3" transform="translate(-5, -10)">
                                <path d="M50 15 A2 2 0 0 0 46 15 A2 2 0 0 0 50 19 A2 2 0 0 0 54 15 A2 2 0 0 0 50 15 Z" fill="#fb7185" />
                            </g>
                        </>
                    )}

                    {/* Body Parts */}
                    <rect x="42" y="70" width="6" height="10" rx="3" fill="url(#hbBody)" />
                    <rect x="52" y="70" width="6" height="10" rx="3" fill="url(#hbBody)" />

                    {/* Left Arm */}
                    <rect x="25" y="52" width="7" height="16" rx="3.5" fill="url(#hbBody)" transform="rotate(20 28 52)" />
                    
                    {/* Right Arm (Waving) */}
                    <g className="bot-arm-wave">
                        <rect x="68" y="52" width="7" height="16" rx="3.5" fill="url(#hbBody)" />
                    </g>
                    
                    {/* Main Torso */}
                    <ellipse cx="50" cy="62" rx="16" ry="14" fill="url(#hbBody)" />

                    {/* Neck Ring */}
                    <ellipse cx="50" cy="48" rx="8" ry="2" fill="#94a3b8" />

                    {/* Headphones/Ears */}
                    <rect x="22" y="28" width="6" height="14" rx="3" fill={botState === 'speaking' ? "url(#hbEar)" : "#60a5fa"} />
                    <rect x="72" y="28" width="6" height="14" rx="3" fill={botState === 'speaking' ? "url(#hbEar)" : "#60a5fa"} />

                    {/* Head */}
                    <rect x="25" y="20" width="50" height="34" rx="14" fill="url(#hbBody)" />
                    {/* Head Gloss */}
                    <path d="M 32 23 Q 50 19 68 23 A 10 10 0 0 0 32 23" fill="#ffffff" opacity="0.6" />

                    {/* Face Screen */}
                    <rect x="30" y="25" width="40" height="22" rx="8" fill="url(#hbScreen)" />

                    {/* Face Details (Cyan Glow) */}
                    <g className="shadow-[0_0_10px_#22d3ee]">
                        {/* Eyes */}
                        {botState === 'listening' ? (
                            <>
                                {/* Happy ^ ^ eyes */}
                                <path d="M 38 34 Q 41 31 44 34" fill="none" stroke="#22d3ee" strokeWidth="2.5" strokeLinecap="round" />
                                <path d="M 56 34 Q 59 31 62 34" fill="none" stroke="#22d3ee" strokeWidth="2.5" strokeLinecap="round" />
                            </>
                        ) : botState === 'speaking' ? (
                            <>
                                {/* Winking > U */}
                                <path d="M 38 32 L 42 34 L 38 36" fill="none" stroke="#22d3ee" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                                <ellipse cx="60" cy="34" rx="2.5" ry="3.5" fill="#22d3ee" />
                            </>
                        ) : botState === 'thinking' ? (
                            <>
                                {/* Looking up/Thinking */}
                                <ellipse cx="40" cy="32" rx="2" ry="2" fill="#22d3ee" />
                                <ellipse cx="60" cy="32" rx="2" ry="2" fill="#22d3ee" />
                                <path d="M 46 28 Q 50 25 54 28" fill="none" stroke="#facc15" strokeWidth="1.5" strokeLinecap="round" className="animate-pulse" />
                            </>
                        ) : (
                            <>
                                {/* Default Idle */}
                                <g className="bot-blink">
                                    <ellipse cx="41" cy="34" rx="2.5" ry="3.5" fill="#22d3ee" />
                                    <ellipse cx="59" cy="34" rx="2.5" ry="3.5" fill="#22d3ee" />
                                </g>
                            </>
                        )}

                        {/* Mouth */}
                        {botState === 'speaking' ? (
                            <path d="M 46 41 Q 50 44 54 41" fill="none" stroke="#22d3ee" strokeWidth="2" strokeLinecap="round" className="bot-mouth-speak" />
                        ) : botState === 'thinking' ? (
                            <path d="M 48 42 L 52 42" fill="none" stroke="#22d3ee" strokeWidth="2" strokeLinecap="round" />
                        ) : (
                            <path d="M 46 41 Q 50 43 54 41" fill="none" stroke="#22d3ee" strokeWidth="2" strokeLinecap="round" />
                        )}
                    </g>
                </svg>
            );
        } else if (type === 'nova') {
            // NOVA (Visor robot with holograms and tablet gestures)
            return (
                <svg viewBox="0 0 100 100" className="w-full h-full drop-shadow-2xl overflow-visible">
                    <defs>
                        <linearGradient id="novaBody" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" stopColor="#ffffff"/>
                            <stop offset="100%" stopColor="#e2e8f0"/>
                        </linearGradient>
                        <linearGradient id="novaScreen" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stopColor="#334155"/>
                            <stop offset="100%" stopColor="#0f172a"/>
                        </linearGradient>
                        <linearGradient id="novaAcc" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" stopColor="#2dd4bf"/>
                            <stop offset="100%" stopColor="#06b6d4"/>
                        </linearGradient>
                        <linearGradient id="novaTablet" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" stopColor="#d946ef"/>
                            <stop offset="100%" stopColor="#db2777"/>
                        </linearGradient>
                    </defs>

                    {/* Background Holograms (Speaking) */}
                    {botState === 'speaking' && (
                        <g className="opacity-70">
                            <rect x="5" y="45" width="20" height="25" rx="2" fill="none" stroke="#a3e635" strokeWidth="1" className="heart-anim-1" />
                            <circle cx="15" cy="50" r="3" fill="#a3e635" className="heart-anim-1" />
                            <rect x="75" y="40" width="25" height="15" rx="2" fill="none" stroke="#facc15" strokeWidth="1.5" className="heart-anim-2" />
                            <path d="M 80 47 L 90 47 M 80 50 L 85 50" stroke="#facc15" strokeWidth="1" className="heart-anim-2" />
                            <circle cx="95" cy="30" r="2" fill="#fb923c" className="animate-ping" />
                            <circle cx="10" cy="70" r="2" fill="#2dd4bf" className="animate-ping" />
                        </g>
                    )}

                    {/* Legs */}
                    <rect x="38" y="75" width="8" height="12" rx="4" fill="url(#novaBody)" />
                    <rect x="54" y="75" width="8" height="12" rx="4" fill="url(#novaBody)" />
                    {/* Feet Accents */}
                    <path d="M 38 82 Q 42 80 46 82 L 46 87 Q 42 89 38 87 Z" fill="url(#novaAcc)" />
                    <path d="M 54 82 Q 58 80 62 82 L 62 87 Q 58 89 54 87 Z" fill="url(#novaAcc)" />

                    {/* Torso */}
                    {botState === 'thinking' ? (
                        /* Leaning forward Torso */
                        <path d="M 35 50 Q 50 48 65 50 L 60 76 Q 50 82 40 76 Z" fill="url(#novaBody)" />
                    ) : (
                        <path d="M 32 50 Q 50 45 68 50 L 60 78 Q 50 84 40 78 Z" fill="url(#novaBody)" />
                    )}
                    
                    {/* Collar/Neck */}
                    <path d="M 35 48 Q 50 56 65 48 L 62 50 Q 50 58 38 50 Z" fill="url(#novaAcc)" />

                    {/* Head Core */}
                    <ellipse cx="50" cy="35" rx="24" ry="20" fill="url(#novaBody)" />
                    
                    {/* Back Ear/Accent */}
                    <path d="M 65 25 Q 75 25 78 35 L 70 40 Z" fill="url(#novaAcc)" />

                    {/* Face Screen */}
                    <rect x="32" y="24" width="36" height="22" rx="10" fill="url(#novaScreen)" />

                    {/* Helmet Brim */}
                    <path d="M 22 30 Q 50 15 78 30 Q 50 25 22 30" fill="#ffffff" />
                    <path d="M 22 30 Q 50 20 78 30 Q 50 28 22 30" fill="#e2e8f0" />
                    
                    {/* Head Logo */}
                    <path d="M 45 20 L 50 24 L 55 18 L 58 20 L 50 28 L 42 22 Z" fill="url(#novaAcc)" />

                    {/* Face Details */}
                    <g className="shadow-[0_0_12px_#34d399]">
                        {/* Eyes */}
                        {botState === 'listening' ? (
                            <>
                                {/* Happy closed eyes ^ ^ */}
                                <path d="M 40 33 Q 43 28 46 33" fill="none" stroke="#4ade80" strokeWidth="3" strokeLinecap="round" />
                                <path d="M 54 33 Q 57 28 60 33" fill="none" stroke="#4ade80" strokeWidth="3" strokeLinecap="round" />
                            </>
                        ) : botState === 'thinking' ? (
                            <>
                                {/* Squinting / joyful curve n n */}
                                <path d="M 38 31 Q 42 28 46 31" fill="none" stroke="#4ade80" strokeWidth="3" strokeLinecap="round" />
                                <path d="M 54 31 Q 58 28 62 31" fill="none" stroke="#4ade80" strokeWidth="3" strokeLinecap="round" />
                            </>
                        ) : botState === 'speaking' ? (
                            <>
                                {/* Wide surprised/talking eyes O O */}
                                <rect x="38" y="28" width="8" height="10" rx="4" fill="#4ade80" />
                                <rect x="54" y="28" width="8" height="10" rx="4" fill="#4ade80" />
                            </>
                        ) : (
                            <>
                                {/* Default rectangular eyes */}
                                <g className="bot-blink">
                                    <rect x="38" y="30" width="8" height="8" rx="2" fill="#4ade80" />
                                    <rect x="54" y="30" width="8" height="8" rx="2" fill="#4ade80" />
                                </g>
                            </>
                        )}
                        
                        {/* Mouth */}
                        {botState === 'speaking' ? (
                            <ellipse cx="50" cy="42" rx="4" ry="2" fill="#4ade80" className="bot-mouth-speak" />
                        ) : botState === 'listening' ? (
                            <path d="M 46 39 Q 50 43 54 39" fill="none" stroke="#4ade80" strokeWidth="2" strokeLinecap="round" />
                        ) : botState === 'thinking' ? (
                            <path d="M 46 41 Q 50 44 54 41" fill="none" stroke="#4ade80" strokeWidth="2" strokeLinecap="round" />
                        ) : (
                            <path d="M 47 41 Q 50 43 53 41" fill="none" stroke="#4ade80" strokeWidth="2" strokeLinecap="round" />
                        )}
                    </g>

                    {/* Arms & Interactive Props */}
                    {botState === 'thinking' ? (
                        <>
                            {/* Holding Tablet */}
                            <rect x="25" y="45" width="22" height="30" rx="2" fill="url(#novaTablet)" transform="rotate(-15 35 60) skewY(-10)" className="shadow-[0_0_15px_#d946ef] animate-pulse" />
                            <path d="M 28 48 L 42 45" stroke="#fbcfe8" strokeWidth="1" transform="rotate(-15 35 60) skewY(-10)" />
                            
                            {/* Hands curling over tablet */}
                            <circle cx="48" cy="65" r="5" fill="url(#novaAcc)" />
                            <circle cx="28" cy="72" r="5" fill="url(#novaAcc)" />
                            {/* Arm curves pointing to hands */}
                            <path d="M 62 55 Q 65 65 48 65" fill="none" stroke="url(#novaBody)" strokeWidth="8" strokeLinecap="round" />
                            <path d="M 38 55 Q 30 72 28 72" fill="none" stroke="url(#novaBody)" strokeWidth="8" strokeLinecap="round" />
                        </>
                    ) : botState === 'speaking' ? (
                        <>
                            {/* Both arms up casting holograms */}
                            <path d="M 32 55 Q 20 50 15 45" fill="none" stroke="url(#novaBody)" strokeWidth="8" strokeLinecap="round" />
                            <path d="M 68 55 Q 80 50 85 45" fill="none" stroke="url(#novaBody)" strokeWidth="8" strokeLinecap="round" />
                            <circle cx="15" cy="45" r="5" fill="url(#novaAcc)" className="shadow-[0_0_10px_#2dd4bf]" />
                            <circle cx="85" cy="45" r="5" fill="url(#novaAcc)" className="shadow-[0_0_10px_#2dd4bf]" />
                        </>
                    ) : botState === 'listening' ? (
                        <>
                            {/* One arm pointing up, one on hip */}
                            <path d="M 32 55 Q 25 65 30 70" fill="none" stroke="url(#novaBody)" strokeWidth="8" strokeLinecap="round" />
                            <circle cx="30" cy="70" r="5" fill="url(#novaAcc)" />
                            
                            <path d="M 68 55 Q 80 40 75 35" fill="none" stroke="url(#novaBody)" strokeWidth="8" strokeLinecap="round" className="bot-arm-wave" />
                            <circle cx="75" cy="35" r="5" fill="url(#novaAcc)" className="bot-arm-wave shadow-[0_0_8px_#facc15]" />
                            <path d="M 82 30 L 88 25 M 85 36 L 90 35 M 75 25 L 75 20" stroke="#facc15" strokeWidth="2" strokeLinecap="round" className="animate-ping" />
                        </>
                    ) : (
                        <>
                            {/* Idle: Waving Arm */}
                            <path d="M 32 55 Q 25 65 32 72" fill="none" stroke="url(#novaBody)" strokeWidth="8" strokeLinecap="round" />
                            <circle cx="32" cy="72" r="5" fill="url(#novaAcc)" />
                            
                            <g className="bot-arm-wave">
                                <path d="M 68 55 Q 75 40 82 35" fill="none" stroke="url(#novaBody)" strokeWidth="8" strokeLinecap="round" />
                                <circle cx="82" cy="35" r="5" fill="url(#novaAcc)" />
                                {/* Waving rays */}
                                <path d="M 88 30 L 92 26 M 92 38 L 96 36 M 85 25 L 87 20" stroke="#2dd4bf" strokeWidth="2" strokeLinecap="round" />
                            </g>
                        </>
                    )}
                </svg>
            );
        }
    };

    return (
        <div 
            className={`relative group flex items-center justify-center cursor-pointer transition-transform duration-500 ease-in-out hover:scale-105 ${className}`}
            onClick={onClick}
            title={botState === 'idle' ? "Click to interact!" : `Your Guide is ${botState}`}
        >
            <style dangerouslySetInnerHTML={{
                __html: `
                @keyframes float {
                    0%, 100% { transform: translateY(0px); }
                    50% { transform: translateY(-8px); }
                }
                @keyframes blink {
                    0%, 96%, 98% { transform: scaleY(1); }
                    97%, 100% { transform: scaleY(0.1); }
                }
                @keyframes speak-mouth {
                    0%, 100% { transform: scale(1, 0.2); }
                    25% { transform: scale(1.2, 0.8); }
                    50% { transform: scale(0.9, 1.2); }
                    75% { transform: scale(1.1, 0.6); }
                }
                @keyframes iris-pulse {
                    0%, 100% { transform: scale(1); opacity: 0.8; }
                    50% { transform: scale(1.1); opacity: 1; }
                }
                @keyframes spin-slow {
                    from { transform: rotate(0deg); }
                    to { transform: rotate(360deg); }
                }
                @keyframes heart-float {
                    0% { transform: translateY(0) scale(0.5); opacity: 0; }
                    20% { opacity: 1; }
                    80% { transform: translateY(-20px) scale(1.2); opacity: 0.8; }
                    100% { transform: translateY(-30px) scale(1.5); opacity: 0; }
                }
                @keyframes bot-arm-wave-anim {
                    0%, 100% { transform: rotate(-30deg); }
                    50% { transform: rotate(-60deg); }
                }
                
                .bot-float { animation: float 4s ease-in-out infinite; }
                .bot-blink { transform-origin: center; animation: blink 4s infinite; }
                .bot-mouth-speak { transform-origin: center; animation: speak-mouth 0.4s infinite alternate; }
                .bot-iris-pulse { transform-origin: center; animation: iris-pulse 0.5s infinite alternate; }
                .animate-spin-slow { animation: spin-slow 8s linear infinite; }
                .animate-spin-reverse-slow { animation: spin-reverse-slow 8s linear infinite; }
                .bot-core-pulse { transform-origin: center; animation: core-pulse 0.6s infinite alternate; }
                .bot-arm-wave { transform-origin: 75% 55%; animation: bot-arm-wave-anim 1.5s ease-in-out infinite; }
                .heart-anim-1 { animation: heart-float 2s ease-in infinite; }
                .heart-anim-2 { animation: heart-float 2.5s ease-in infinite 0.5s; }
                .heart-anim-3 { animation: heart-float 2.2s ease-in infinite 1s; }
            `}} />

            {/* Glowing Aura */}
            {botState !== 'idle' && (
                <>
                    <div className={`absolute inset-[-10px] rounded-full border-2 ${ringColor} animate-ping opacity-60 z-0`}></div>
                    {botState !== 'thinking' && (
                        <div className={`absolute inset-[-4px] rounded-full border-2 ${ringPingColor} animate-ping opacity-40 animation-delay-200 z-0`}></div>
                    )}
                </>
            )}

            {/* SVG Character */}
            <div className={`relative z-10 w-16 h-16 md:w-20 md:h-20 bot-float transform transition-transform ${botState === 'speaking' ? 'scale-110' : ''}`}>
                {renderCharacterSVG()}
            </div>
        </div>
    );
};
