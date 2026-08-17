import React, { useEffect, useRef, useState } from 'react';
import {
    webrtcCallService,
    CallState,
    IncomingCallInfo,
    PeerInfo,
} from '../services/webrtcCallService';

/**
 * Global call overlay. Mount once near the app root. Owns the webrtcCallService
 * handlers, renders the incoming-call ring, outgoing "calling…" state, and the
 * in-call window (audio or video) with mute / camera / hang-up controls.
 */
export const CallOverlay: React.FC = () => {
    const [state, setState] = useState<CallState>('idle');
    const [peer, setPeer] = useState<PeerInfo | null>(null);
    const [incoming, setIncoming] = useState<IncomingCallInfo | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [micOn, setMicOn] = useState(true);
    const [camOn, setCamOn] = useState(true);

    const localRef = useRef<HTMLVideoElement>(null);
    const remoteRef = useRef<HTMLVideoElement>(null);
    const localStreamRef = useRef<MediaStream | null>(null);
    const remoteStreamRef = useRef<MediaStream | null>(null);

    useEffect(() => {
        webrtcCallService.init();
        webrtcCallService.setHandlers({
            onStateChange: (s, p) => {
                setState(s);
                setPeer(p);
                if (s === 'idle') {
                    setIncoming(null);
                    setMicOn(true);
                    setCamOn(true);
                }
            },
            onIncomingCall: (info) => { setIncoming(info); setError(null); },
            onLocalStream: (stream) => {
                localStreamRef.current = stream;
                if (localRef.current) localRef.current.srcObject = stream;
            },
            onRemoteStream: (stream) => {
                remoteStreamRef.current = stream;
                if (remoteRef.current) remoteRef.current.srcObject = stream;
            },
            onError: (msg) => {
                setError(msg);
                window.setTimeout(() => setError((e) => (e === msg ? null : e)), 4000);
            },
        });
    }, []);

    // Re-bind streams whenever the video elements (re)mount for a given state.
    useEffect(() => {
        if (localRef.current && localStreamRef.current) localRef.current.srcObject = localStreamRef.current;
        if (remoteRef.current && remoteStreamRef.current) remoteRef.current.srcObject = remoteStreamRef.current;
    }, [state]);

    const isVideoCall = (incoming?.video ?? false) || camOn;

    if (state === 'idle' && !error) return null;

    // ── Error toast (also shows briefly after a call ends) ──────────────────────
    const errorToast = error && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[10000] bg-red-600 text-white text-sm px-4 py-2 rounded-lg shadow-lg">
            {error}
        </div>
    );

    // ── Incoming call ring ──────────────────────────────────────────────────────
    if (state === 'ringing' && incoming) {
        return (
            <>
                <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 backdrop-blur-sm">
                    <div className="bg-slate-900 border border-slate-700 rounded-2xl p-8 w-[340px] text-center text-white shadow-2xl">
                        <div className="w-20 h-20 rounded-full bg-emerald-600/20 border border-emerald-500/40 mx-auto flex items-center justify-center text-3xl font-semibold mb-4 animate-pulse">
                            {(incoming.fromName || '?')[0]?.toUpperCase()}
                        </div>
                        <p className="text-lg font-semibold">{incoming.fromName}</p>
                        <p className="text-sm text-slate-400 mb-6">
                            Incoming {incoming.video ? 'video' : 'voice'} call…
                        </p>
                        <div className="flex justify-center gap-4">
                            <button
                                onClick={() => webrtcCallService.rejectCall()}
                                className="flex-1 bg-red-600 hover:bg-red-500 py-2.5 rounded-lg font-medium"
                            >Decline</button>
                            <button
                                onClick={() => webrtcCallService.acceptCall()}
                                className="flex-1 bg-emerald-600 hover:bg-emerald-500 py-2.5 rounded-lg font-medium"
                            >Accept</button>
                        </div>
                    </div>
                </div>
                {errorToast}
            </>
        );
    }

    // ── Outgoing / connecting / active ─────────────────────────────────────────
    const label =
        state === 'calling' ? `Calling ${peer?.name ?? ''}…`
        : state === 'connecting' ? 'Connecting…'
        : peer?.name ?? '';

    return (
        <>
            <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-slate-950/90 backdrop-blur-sm">
                <div className="relative w-full h-full max-w-4xl max-h-[80vh] m-4 bg-slate-900 rounded-2xl overflow-hidden border border-slate-700 flex flex-col">
                    {/* Remote video / avatar */}
                    <div className="flex-1 relative bg-black flex items-center justify-center">
                        <video
                            ref={remoteRef}
                            autoPlay
                            playsInline
                            className={`w-full h-full object-contain ${state === 'in-call' && isVideoCall ? '' : 'hidden'}`}
                        />
                        {(state !== 'in-call' || !isVideoCall) && (
                            <div className="text-center text-white">
                                <div className="w-24 h-24 rounded-full bg-slate-700 mx-auto flex items-center justify-center text-4xl font-semibold mb-4">
                                    {(peer?.name || '?')[0]?.toUpperCase()}
                                </div>
                                <p className="text-lg font-medium">{label}</p>
                            </div>
                        )}
                        {/* Local preview (PiP) */}
                        <video
                            ref={localRef}
                            autoPlay
                            playsInline
                            muted
                            className={`absolute bottom-4 right-4 w-40 h-28 object-cover rounded-lg border border-slate-600 bg-black ${camOn && localStreamRef.current ? '' : 'hidden'}`}
                        />
                        {state === 'in-call' && (
                            <div className="absolute top-3 left-4 text-xs text-white/80 bg-black/40 px-2 py-1 rounded">
                                {peer?.name}
                            </div>
                        )}
                    </div>

                    {/* Controls */}
                    <div className="flex items-center justify-center gap-4 py-4 bg-slate-900">
                        <button
                            onClick={() => setMicOn(webrtcCallService.toggleMic())}
                            title={micOn ? 'Mute microphone' : 'Unmute microphone'}
                            aria-label={micOn ? 'Mute microphone' : 'Unmute microphone'}
                            className={`w-12 h-12 rounded-full flex items-center justify-center ${micOn ? 'bg-slate-700 hover:bg-slate-600' : 'bg-red-600 hover:bg-red-500'} text-white`}
                        >
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/>
                                {!micOn && <line x1="3" y1="3" x2="21" y2="21"/>}
                            </svg>
                        </button>

                        {(isVideoCall || camOn) && (
                            <button
                                onClick={() => setCamOn(webrtcCallService.toggleCam())}
                                title={camOn ? 'Turn camera off' : 'Turn camera on'}
                                aria-label={camOn ? 'Turn camera off' : 'Turn camera on'}
                                className={`w-12 h-12 rounded-full flex items-center justify-center ${camOn ? 'bg-slate-700 hover:bg-slate-600' : 'bg-red-600 hover:bg-red-500'} text-white`}
                            >
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                    <path d="m23 7-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
                                    {!camOn && <line x1="1" y1="1" x2="23" y2="23"/>}
                                </svg>
                            </button>
                        )}

                        <button
                            onClick={() => webrtcCallService.endCall()}
                            title="Hang up"
                            aria-label="Hang up"
                            className="w-14 h-12 rounded-full bg-red-600 hover:bg-red-500 text-white flex items-center justify-center"
                        >
                            <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M12 9c-1.6 0-3.15.25-4.6.72v3.1c0 .39-.23.74-.56.9-.98.49-1.87 1.12-2.66 1.85-.18.18-.43.28-.7.28-.28 0-.53-.11-.71-.29L.29 13.08a.956.956 0 0 1-.29-.7c0-.28.11-.53.29-.71C3.34 8.78 7.46 7 12 7s8.66 1.78 11.71 4.67c.18.18.29.43.29.71 0 .28-.11.53-.29.71l-1.78 1.78c-.18.18-.43.29-.71.29-.27 0-.52-.1-.7-.28a11.27 11.27 0 0 0-2.66-1.85.996.996 0 0 1-.56-.9v-3.1C15.15 9.25 13.6 9 12 9z"/>
                            </svg>
                        </button>
                    </div>
                </div>
            </div>
            {errorToast}
        </>
    );
};

export default CallOverlay;
