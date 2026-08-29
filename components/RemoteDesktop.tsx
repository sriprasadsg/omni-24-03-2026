import React, { useEffect, useRef, useState } from 'react';
import { AlertTriangleIcon, MonitorIcon } from './icons';
import { startRemoteSession } from '../services/apiService';

interface RemoteDesktopProps {
    agentId: string;
    sessionId?: string;
    mode?: 'view' | 'control';
}

export const RemoteDesktop: React.FC<RemoteDesktopProps> = ({ agentId, sessionId: sessionIdProp, mode = 'view' }) => {
    const [isConnected, setIsConnected] = useState(false);
    const [fps, setFps] = useState(0);
    const [hasFrames, setHasFrames] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [statusMsg, setStatusMsg] = useState('Requesting desktop session…');
    const [controlState, setControlState] = useState<'awaiting_consent' | 'active' | 'ended' | null>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const frameCountRef = useRef(0);
    const lastFpsTimeRef = useRef(Date.now());
    // Mirrors `hasFrames` state but readable synchronously from closures
    // (e.g. the no-frames timeout below) without going stale.
    const hasFramesRef = useRef(false);
    // React 18 StrictMode (dev only) mounts this effect, cleans it up, then
    // mounts it again with the same props — synchronously, before the first
    // mount's startRemoteSession() POST has resolved. `cancelled` alone
    // doesn't stop that POST from firing twice, since each invocation gets
    // its own closure. This ref survives the synthetic remount (same
    // component instance), so the second invocation sees the key already
    // claimed and skips re-requesting a session — while still re-requesting
    // on a genuine agentId/sessionIdProp change.
    const initedForRef = useRef<string | null>(null);

    const renderFrame = (base64Data: string) => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        const img = new Image();
        img.onload = () => ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        img.src = `data:image/jpeg;base64,${base64Data}`;
    };

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
                        // Agent→browser consent/activity lifecycle. Rendering the
                        // four visual states is Plan 05's job — for now just hold
                        // the value so the state machine starts accumulating.
                        setControlState(payload.state);
                    } else if (payload.type === 'error' && payload.message) {
                        // Agent-reported capture failure (e.g. no interactive
                        // desktop session, or unsupported platform) — surface
                        // it instead of leaving the viewer waiting forever.
                        setError(String(payload.message));
                        setStatusMsg('');
                    }
                } catch { /* ignore non-JSON */ }
            };

            ws.onerror = () => { setError('Stream connection failed'); setIsConnected(false); };
            ws.onclose = () => { setIsConnected(false); setFps(0); };

            // Defense in depth: if the agent connects but never sends a frame
            // or error message at all (e.g. it's offline, or a future capture
            // path fails before it can report), don't leave the UI spinning
            // forever with no signal. 45s, not 15s: the agent only picks up
            // the start_remote_session instruction on its next poll cycle
            // (observed ~26-33s), so a shorter timeout routinely fires before
            // the agent has even joined the tunnel.
            setTimeout(() => {
                if (!cancelled && !hasFramesRef.current) {
                    setError((prev) => prev ?? 'No video received from the agent within 45s — it may be offline, lack an interactive desktop session, or not support remote desktop on its platform.');
                }
            }, 45000);
        };

        const init = async () => {
            const key = `${agentId}:${sessionIdProp || ''}`;
            if (initedForRef.current === key) return;
            initedForRef.current = key;

            if (sessionIdProp) {
                openWs(sessionIdProp, mode);
                return;
            }
            // No sessionId supplied — start a new desktop session via the API.
            const sessionType = mode === 'control' ? 'control' : 'desktop';
            setStatusMsg('Requesting desktop session…');
            const resp = await startRemoteSession(agentId, 'vnc', sessionType);
            if (cancelled) return;
            if (resp?.session_id) {
                openWs(resp.session_id);
            } else {
                setError(resp?.error ? String(resp.error) : 'Failed to start desktop session');
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
    }, [agentId, sessionIdProp]);

    return (
        <div className="flex flex-col h-full bg-slate-950 p-4 rounded-lg border border-slate-800">
            <div className="flex justify-between items-center mb-4">
                <div className="flex items-center space-x-2">
                    <MonitorIcon size={20} className={isConnected ? 'text-green-400' : 'text-slate-500'} />
                    <h3 className="text-sm font-semibold text-slate-200">
                        Remote Desktop View
                        {isConnected && <span className="ml-2 text-xs font-mono text-slate-500">({fps} FPS)</span>}
                    </h3>
                </div>
                <div>
                    {!error && statusMsg && (
                        <span className="text-xs text-yellow-500 animate-pulse">{statusMsg}</span>
                    )}
                    {error && (
                        <span className="text-xs text-red-400 flex items-center gap-1">
                            <AlertTriangleIcon size={12} /> {error}
                        </span>
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
                <canvas
                    ref={canvasRef}
                    width={800}
                    height={600}
                    className={`max-w-full max-h-full object-contain ${!hasFrames ? 'hidden' : ''}`}
                    onMouseMove={mode === 'control' ? (event) => {
                        const canvas = canvasRef.current;
                        const ws = wsRef.current;
                        if (!canvas || !ws || ws.readyState !== WebSocket.OPEN) return;
                        const x = Math.min(1, Math.max(0, event.nativeEvent.offsetX / canvas.clientWidth));
                        const y = Math.min(1, Math.max(0, event.nativeEvent.offsetY / canvas.clientHeight));
                        ws.send(JSON.stringify({ type: 'input', kind: 'mousemove', x, y }));
                    } : undefined}
                />
            </div>

            <div className="mt-3 text-xs text-slate-600 text-center">
                Stream is relayed via an encrypted WebSocket tunnel.
            </div>
        </div>
    );
};
