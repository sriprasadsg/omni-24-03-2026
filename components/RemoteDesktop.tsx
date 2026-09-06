import React, { useEffect, useRef, useState, useCallback } from 'react';
import { AlertTriangleIcon, MonitorIcon, XIcon, ShieldCheckIcon, UserIcon, BuildingIcon, LoaderIcon, CheckCircleIcon, ChevronRightIcon } from './icons';
import { startRemoteSession, disconnectRemoteSession } from '../services/apiService';
import { resolveKeyEventToFrame, normalizeCanvasPoint } from '../types';

interface RemoteDesktopProps {
    agentId: string;
    sessionId?: string;
    mode?: 'view' | 'control';
    hostname?: string;
}

export const RemoteDesktop: React.FC<RemoteDesktopProps> = ({ agentId, sessionId: sessionIdProp, mode = 'view', hostname }) => {
    const [isConnected, setIsConnected] = useState(false);
    const [fps, setFps] = useState(0);
    const [hasFrames, setHasFrames] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [statusMsg, setStatusMsg] = useState('Requesting desktop session…');
    const [controlState, setControlState] = useState<'awaiting_consent' | 'active' | 'ended' | null>(null);
    const [controlReason, setControlReason] = useState<string | null>(null);
    const [controlMessage, setControlMessage] = useState<string | null>(null);
    const [requesterName, setRequesterName] = useState<string>('');
    const [requesterEmail, setRequesterEmail] = useState<string>('');
    const [tenantName, setTenantName] = useState<string>('');
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const frameCountRef = useRef(0);
    const lastFpsTimeRef = useRef(Date.now());
    const hasFramesRef = useRef(false);
    const initedForRef = useRef<string | null>(null);
    const keysDownRef = useRef<Set<string>>(new Set());
    const [disconnectConfirm, setDisconnectConfirm] = useState(false);
    const disconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    // True while the agent holds the endpoint user's consent prompt open; the
    // 45s no-video watchdog must not fire during that window because frames
    // are (correctly) gated until the user accepts.
    const awaitingConsentRef = useRef(false);

    const getControlStateCopy = useCallback((): string => {
        if (controlState === 'ended') {
            switch (controlReason) {
                case 'consent_declined':
                    return 'Endpoint user declined the control request.';
                case 'consent_timed_out':
                    return 'Endpoint user did not respond in time. The request has expired.';
                case 'no_interactive_desktop':
                    return 'The remote machine has no active interactive desktop session.';
                case 'wrong_platform':
                    return 'Remote control is not supported on the endpoint platform.';
                case 'already_controlled':
                    return `Already controlled by ${requesterName || 'another admin'}.`;
                case 'tunnel_drop':
                    return 'Connection lost. Reconnecting requires fresh approval from the endpoint user.';
                case 'relay_failed':
                    return 'Control session accepted but input relay failed. Session ended.';
                default:
                    if (controlMessage) return controlMessage;
                    return 'Control session ended.';
            }
        }
        return '';
    }, [controlReason, controlMessage, requesterName]);

    const renderFrame = (base64Data: string) => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        const img = new Image();
        img.onload = () => ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        img.src = `data:image/jpeg;base64,${base64Data}`;
    };

    const sendInput = useCallback((frame: object): void => {
        const ws = wsRef.current;
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        if (controlState !== 'active') return;
        try {
            ws.send(JSON.stringify(frame));
        } catch { /* tunnel already closing */ }
    }, [controlState]);

    const sendStop = useCallback((): void => {
        const ws = wsRef.current;
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        try {
            ws.send(JSON.stringify({ type: 'control_stop' }));
        } catch { /* tunnel already closing */ }
    }, []);

    const handleDisconnect = useCallback(async () => {
        if (disconnectConfirm) {
            if (disconnectTimerRef.current) clearTimeout(disconnectTimerRef.current);
            if (sessionIdProp) {
                await disconnectRemoteSession(sessionIdProp);
            }
            sendStop();
            setDisconnectConfirm(false);
            return;
        }
        setDisconnectConfirm(true);
        disconnectTimerRef.current = setTimeout(() => setDisconnectConfirm(false), 4000);
    }, [disconnectConfirm, sessionIdProp, sendStop]);

    useEffect(() => {
        return () => {
            if (disconnectTimerRef.current) clearTimeout(disconnectTimerRef.current);
        };
    }, []);

    useEffect(() => {
        let cancelled = false;

        const openWs = (sid: string, mode: 'view' | 'control' = 'view') => {
            hasFramesRef.current = false;
            const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const token = sessionStorage.getItem('token') || '';
            const wsUrl = `${wsProtocol}//${window.location.host}/api/tunnel/${sid}/${mode === 'control' ? 'user' : 'viewer'}?token=${encodeURIComponent(token)}`;

            if (cancelled) return;
            setStatusMsg('Connecting to desktop stream…');

            const ws = new WebSocket(wsUrl);
            wsRef.current = ws;

            ws.onopen = () => { setIsConnected(true); setError(null); setStatusMsg('Waiting for agent to start streaming…'); };

            ws.onmessage = (event) => {
                try {
                    const payload = JSON.parse(event.data);
                    if (payload.type === 'frame' && payload.data) {
                        renderFrame(payload.data);
                        if (!hasFramesRef.current) { hasFramesRef.current = true; setHasFrames(true); setStatusMsg(''); }
                        frameCountRef.current++;
                        const now = Date.now();
                        if (now - lastFpsTimeRef.current >= 1000) {
                            setFps(frameCountRef.current);
                            frameCountRef.current = 0;
                            lastFpsTimeRef.current = now;
                        }
                    } else if (payload.type === 'control_state') {
                        setControlState(payload.state);
                        setControlReason(payload.reason ?? null);
                        setControlMessage(payload.message ?? null);
                        if (payload.requester_name) setRequesterName(String(payload.requester_name));
                        if (payload.requester_email) setRequesterEmail(String(payload.requester_email));
                        if (payload.tenant_name) setTenantName(String(payload.tenant_name));
                        if (payload.state === 'active') {
                            awaitingConsentRef.current = false;
                            setStatusMsg('');
                        } else if (payload.state === 'awaiting_consent') {
                            awaitingConsentRef.current = true;
                            setStatusMsg('Awaiting endpoint user consent…');
                        } else if (payload.state === 'ended') {
                            awaitingConsentRef.current = false;
                            setStatusMsg('');
                        }
                    } else if (payload.type === 'error' && payload.message) {
                        setError(String(payload.message));
                        setStatusMsg('');
                    }
                } catch { /* ignore non-JSON */ }
            };

            ws.onerror = () => { setError('Stream connection failed'); setIsConnected(false); };
            ws.onclose = (ev) => {
                setIsConnected(false);
                setFps(0);
                if (!hasFramesRef.current && !cancelled) {
                    if (ev.code === 4401) setError('Authentication failed — token may be expired. Refresh the page.');
                    else if (ev.code === 4403) setError('Access denied — session not found or tenant mismatch. The agent may have rejected the connection.');
                }
            };

            setTimeout(() => {
                if (!cancelled && !hasFramesRef.current && !awaitingConsentRef.current) {
                    setError((prev) => prev ?? 'No video received from the agent within 45s — it may be offline, lack an interactive desktop session, or not support remote desktop on its platform.');
                }
            }, 45000);
        };

        const init = async () => {
            const key = `${agentId}:${sessionIdProp || ''}:${mode}`;
            if (initedForRef.current === key) return;
            initedForRef.current = key;

            if (sessionIdProp) {
                openWs(sessionIdProp, mode);
                return;
            }
            const sessionType = mode === 'control' ? 'control' : 'desktop';
            setStatusMsg('Requesting desktop session…');
            // ponytail: timed-out session may still land server-side; add TTL/track once a control registry exists
            const TIMEOUT_MS = 20000;
            const resp = await Promise.race([
                startRemoteSession(agentId, 'vnc', sessionType),
                new Promise<'timeout'>((resolve) => setTimeout(() => resolve('timeout'), TIMEOUT_MS)),
            ]);
            if (resp === 'timeout') {
                setError('Remote desktop request timed out — agent unreachable');
                setStatusMsg('');
                return;
            }
            if (cancelled) return;
            if (resp?.session_id) {
                openWs(resp.session_id, mode);
            } else {
                const errText = resp?.error
                    ? (typeof resp.error === 'string' ? resp.error : String(resp.error))
                    : 'Failed to start desktop session';
                const statusHint = resp?.status === 403 ? ' — missing permission' : resp?.status === 409 ? ' — session already active' : resp?.status === 404 ? ' — agent not found' : resp?.status === 401 ? ' — token expired' : '';
                setError(errText + statusHint);
                setStatusMsg('');
            }
        };

        init().catch(e => { if (!cancelled) setError(String(e)); });

        return () => {
            cancelled = true;
            if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                wsRef.current.close();
            }
        };
    }, [agentId, sessionIdProp, mode]);

    const handleMouseMove = useCallback((event: React.MouseEvent<HTMLCanvasElement>) => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const { x, y } = normalizeCanvasPoint(event.nativeEvent.offsetX, event.nativeEvent.offsetY, canvas.clientWidth, canvas.clientHeight);
        sendInput({ type: 'input', kind: 'mousemove', x, y });
    }, [sendInput]);

    const handleMouseDown = useCallback((event: React.MouseEvent<HTMLCanvasElement>) => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const { x, y } = normalizeCanvasPoint(event.nativeEvent.offsetX, event.nativeEvent.offsetY, canvas.clientWidth, canvas.clientHeight);
        const buttonMap: Record<number, number> = { 0: 0, 1: 1, 2: 2 };
        sendInput({ type: 'input', kind: 'mousedown', button: buttonMap[event.button] ?? 0, x, y });
    }, [sendInput]);

    const handleMouseUp = useCallback((event: React.MouseEvent<HTMLCanvasElement>) => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const { x, y } = normalizeCanvasPoint(event.nativeEvent.offsetX, event.nativeEvent.offsetY, canvas.clientWidth, canvas.clientHeight);
        const buttonMap: Record<number, number> = { 0: 0, 1: 1, 2: 2 };
        sendInput({ type: 'input', kind: 'mouseup', button: buttonMap[event.button] ?? 0, x, y });
    }, [sendInput]);

    const handleWheel = useCallback((event: React.WheelEvent<HTMLCanvasElement>) => {
        event.preventDefault();
        sendInput({ type: 'input', kind: 'wheel', deltaX: event.deltaX, deltaY: event.deltaY });
    }, [sendInput]);

    const handleKeyDown = useCallback((event: React.KeyboardEvent) => {
        event.preventDefault();
        const frame = resolveKeyEventToFrame(event);
        if (frame) {
            sendInput({ type: 'input', kind: 'keydown', ...frame });
        }
        keysDownRef.current.add(event.code);
    }, [sendInput]);

    const handleKeyUp = useCallback((event: React.KeyboardEvent) => {
        event.preventDefault();
        const frame = resolveKeyEventToFrame(event);
        if (frame) {
            sendInput({ type: 'input', kind: 'keyup', ...frame });
        }
        keysDownRef.current.delete(event.code);
    }, [sendInput]);

    const canvasClasses = [
        'max-w-full max-h-full object-contain',
        !hasFrames ? 'hidden' : '',
        controlState === 'active' ? 'cursor-crosshair ring-2 ring-emerald-400' : '',
        controlState === 'awaiting_consent' ? 'cursor-wait opacity-60' : '',
    ].filter(Boolean).join(' ');

    return (
        <div className="flex flex-col h-full bg-slate-950 p-4 rounded-lg border border-slate-800">
            <div className="flex justify-between items-center mb-4">
                <div className="flex items-center space-x-2 truncate max-w-[60%]">
                    <MonitorIcon size={20} className={isConnected ? 'text-green-400' : 'text-slate-500'} />
                    <h3 className="text-sm font-semibold text-slate-200 truncate">
                        Remote Desktop View
                        {isConnected && <span className="ml-2 text-xs font-mono text-slate-500">({fps} FPS)</span>}
                        {hostname && <span className="ml-2 text-xs text-slate-500 truncate">{hostname}</span>}
                    </h3>
                </div>
                <div className="flex items-center gap-2">
                    {!error && statusMsg && (
                        <span className="text-xs text-yellow-500 animate-pulse">{statusMsg}</span>
                    )}
                    {error && (
                        <span className="text-xs text-red-400 flex items-center gap-1">
                            <AlertTriangleIcon size={12} /> {error}
                        </span>
                    )}
                    {mode === 'control' && controlState === 'active' && (
                        <button
                            onClick={handleDisconnect}
                            className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded transition-colors ${
                                disconnectConfirm
                                    ? 'bg-red-700 text-red-200'
                                    : 'bg-red-600 hover:bg-red-700 text-white'
                            }`}
                        >
                            <XIcon size={12} />
                            {disconnectConfirm ? 'Confirm Disconnect' : 'Disconnect'}
                        </button>
                    )}
                </div>
            </div>

            <div className="flex-1 bg-black rounded border border-slate-700 relative overflow-hidden flex items-center justify-center">
                {!hasFrames && !error && (
                    <div className="text-center">
                        <MonitorIcon size={48} className="mx-auto text-slate-700 mb-2" />
                        <p className="text-slate-500 text-sm">{statusMsg || 'Waiting for video stream…'}</p>
                        {isConnected && (
                            <p className="text-slate-600 text-xs mt-1">Connected to relay — waiting for agent to open the stream.</p>
                        )}
                    </div>
                )}
                {error && (
                    <div className="text-center">
                        <AlertTriangleIcon size={40} className="mx-auto text-red-600 mb-2" />
                        <p className="text-red-400 text-sm">{error}</p>
                        <p className="text-slate-500 text-xs mt-1">Ensure the agent is online and has the remote-desktop capability enabled.</p>
                    </div>
                )}

                {/* Persistent stop bar — visible only in active control mode */}
                {mode === 'control' && controlState === 'active' && (
                    <div className="absolute top-3 left-3 right-3 z-10 flex items-center justify-between bg-slate-900/95 border border-red-500/50 rounded-lg px-4 py-2 shadow-lg">
                        <div className="flex items-center gap-2">
                            <ShieldCheckIcon size={16} className="text-green-400" />
                            <span className="text-xs text-slate-300 font-medium">Remote control active</span>
                        </div>
                        <button
                            onClick={sendStop}
                            className="flex items-center gap-1.5 bg-red-600 hover:bg-red-700 text-white text-xs font-semibold px-3 py-1.5 rounded transition-colors"
                        >
                            <XIcon size={12} />
                            Stop Control
                        </button>
                    </div>
                )}

                {/* Awaiting consent state — dimmed with pulsing amber badge */}
                {mode === 'control' && controlState === 'awaiting_consent' && (
                    <div className="absolute inset-0 z-20 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm">
                        <div className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-6 max-w-sm w-full mx-4">
                            <div className="flex items-center gap-3 mb-4">
                                <div className="w-10 h-10 rounded-full bg-amber-500/20 flex items-center justify-center animate-pulse">
                                    <LoaderIcon size={20} className="text-amber-400 animate-spin" />
                                </div>
                                <div>
                                    <h3 className="text-slate-100 font-semibold text-sm">Remote Control Request</h3>
                                    <p className="text-slate-500 text-xs">Awaiting endpoint user response…</p>
                                </div>
                            </div>
                            <div className="space-y-2 mb-4">
                                {requesterName && (
                                    <div className="flex items-center gap-2 text-xs text-slate-400">
                                        <UserIcon size={12} />
                                        <span>{requesterName}</span>
                                        {requesterEmail && <span className="text-slate-600">&lt;{requesterEmail}&gt;</span>}
                                    </div>
                                )}
                                {tenantName && (
                                    <div className="flex items-center gap-2 text-xs text-slate-400">
                                        <BuildingIcon size={12} />
                                        <span>{tenantName}</span>
                                    </div>
                                )}
                            </div>
                            <div className="bg-slate-800/50 rounded-lg p-3 mb-4">
                                <p className="text-slate-400 text-xs">
                                    Someone is requesting to view and control your desktop. While control is active, all keyboard and mouse input will be forwarded to your machine.
                                </p>
                            </div>
                            {controlMessage && (
                                <p className="text-yellow-500 text-xs mb-3">{controlMessage}</p>
                            )}
                            <div className="flex items-center gap-2">
                                <div className="flex-1 h-1 bg-slate-700 rounded-full overflow-hidden">
                                    <div className="h-full bg-amber-500 animate-pulse" style={{ width: '60%' }} />
                                </div>
                                <span className="text-slate-500 text-xs">Waiting…</span>
                            </div>
                        </div>
                    </div>
                )}

                {/* Control active state — emerald ring, crosshair cursor, solid emerald badge with pulsing dot */}
                {mode === 'control' && controlState === 'active' && (
                    <div className="absolute top-3 left-3 z-30 flex items-center gap-1.5 bg-emerald-500/20 border border-emerald-500/50 rounded-full px-3 py-1 shadow-lg">
                        <div className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse" />
                        <span className="text-xs text-emerald-300 font-medium">CONTROL ACTIVE</span>
                    </div>
                )}

                {/* Session ended overlay — red banner */}
                {mode === 'control' && controlState === 'ended' && (
                    <div className="absolute inset-0 z-20 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm">
                        <div className="text-center">
                            <XIcon size={32} className="mx-auto text-slate-600 mb-2" />
                            <p className="text-slate-400 text-sm font-medium">Control Ended</p>
                            {getControlStateCopy() && (
                                <p className="text-red-400 text-xs mt-1">{getControlStateCopy()}</p>
                            )}
                            {controlReason && controlReason !== 'tunnel_drop' && controlReason !== 'relay_failed' && controlReason !== 'consent_declined' && controlReason !== 'consent_timed_out' && (
                                <p className="text-slate-500 text-xs mt-1">{controlReason}</p>
                            )}
                        </div>
                    </div>
                )}

                <canvas
                    ref={canvasRef}
                    width={800}
                    height={600}
                    className={canvasClasses}
                    onMouseMove={controlState === 'active' ? handleMouseMove : undefined}
                    onMouseDown={controlState === 'active' ? handleMouseDown : undefined}
                    onMouseUp={controlState === 'active' ? handleMouseUp : undefined}
                    onWheel={controlState === 'active' ? handleWheel : undefined}
                    onKeyDown={controlState === 'active' ? handleKeyDown : undefined}
                    onKeyUp={controlState === 'active' ? handleKeyUp : undefined}
                    tabIndex={controlState === 'active' ? 0 : -1}
                />

                {/* Invisible keyboard sink — captures focus for control mode */}
                {controlState === 'active' && (
                    <input
                        autoFocus
                        className="absolute opacity-0 w-0 h-0"
                        onKeyDown={handleKeyDown}
                        onKeyUp={handleKeyUp}
                    />
                )}
            </div>

            <div className="mt-3 text-xs text-slate-600 text-center">
                Stream is relayed via an encrypted WebSocket tunnel.
            </div>
        </div>
    );
};