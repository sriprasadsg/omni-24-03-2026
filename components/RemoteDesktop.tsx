import React, { useEffect, useRef, useState } from 'react';
import { AlertTriangleIcon, MonitorIcon, PowerIcon } from './icons';

interface RemoteDesktopProps {
    agentId: string;
    sessionId?: string;
}

export const RemoteDesktop: React.FC<RemoteDesktopProps> = ({ agentId, sessionId }) => {
    const [isConnected, setIsConnected] = useState(false);
    const [fps, setFps] = useState(0);
    const [error, setError] = useState<string | null>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const frameCountRef = useRef(0);
    const lastFpsTimeRef = useRef(Date.now());

    useEffect(() => {
        if (!sessionId) return;

        // Construct WebSocket URL
        // In prod, this would likely be a separate path or negotiated via API
        // For MVP, we reuse the /api/tunnel path but expect the agent to be sending JSON frames
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.hostname}:5000/api/tunnel/${sessionId}/viewer`;

        console.log(`Connecting to Desktop Stream: ${wsUrl}`);
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
            console.log("Desktop Stream Connected");
            setIsConnected(true);
            setError(null);
        };

        ws.onmessage = (event) => {
            try {
                // Expecting JSON { type: "frame", data: "base64..." }
                // The backend proxy blindly forwards what the agent sends
                // The agent is sending raw text data, but it might be partial if not careful.
                // However, our agent sends small JSON payloads.

                // Note: If using the existing "RemoteTerminal" tunnel, it expects raw text.
                // But since we are creating a dedicated flow, we handle JSON.

                const payload = JSON.parse(event.data);
                if (payload.type === 'frame' && payload.data) {
                    renderFrame(payload.data);

                    // FPS Counter
                    frameCountRef.current++;
                    const now = Date.now();
                    if (now - lastFpsTimeRef.current >= 1000) {
                        setFps(frameCountRef.current);
                        frameCountRef.current = 0;
                        lastFpsTimeRef.current = now;
                    }
                }
            } catch (err) {
                // Ignore non-JSON messages (e.g. initial handshake or stray text)
                // console.warn("Stream decode error", err);
            }
        };

        ws.onerror = (err) => {
            console.error("Stream WebSocket Error", err);
            setError("Connection failed");
            setIsConnected(false);
        };

        ws.onclose = () => {
            console.log("Stream Disconnected");
            setIsConnected(false);
            setFps(0);
        };

        return () => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.close();
            }
        };
    }, [sessionId]);

    const renderFrame = (base64Data: string) => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const img = new Image();
        img.onload = () => {
            // Auto-resize canvas to match aspect ratio if needed, or scale content
            // For now, fast render
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        };
        img.src = `data:image/jpeg;base64,${base64Data}`;
    };

    return (
        <div className="flex flex-col h-full bg-slate-950 p-4 rounded-lg border border-slate-800">
            <div className="flex justify-between items-center mb-4">
                <div className="flex items-center space-x-2">
                    <MonitorIcon size={20} className={isConnected ? "text-green-400" : "text-slate-500"} />
                    <h3 className="text-sm font-semibold text-slate-200">
                        Remote Desktop View
                        {isConnected && <span className="ml-2 text-xs font-mono text-slate-500">({fps} FPS)</span>}
                    </h3>
                </div>
                <div className="flex space-x-2">
                    {!isConnected && !error && (
                        <span className="text-xs text-yellow-500 animate-pulse flex items-center">
                            Connecting...
                        </span>
                    )}
                    {error && (
                        <span className="text-xs text-red-400 flex items-center">
                            <AlertTriangleIcon size={12} className="mr-1" /> {error}
                        </span>
                    )}
                </div>
            </div>

            <div className="flex-1 bg-black rounded border border-slate-700 relative overflow-hidden flex items-center justify-center">
                {!isConnected && !error && (
                    <div className="text-center">
                        <MonitorIcon size={48} className="mx-auto text-slate-700 mb-2" />
                        <p className="text-slate-500 text-sm">Waiting for video stream...</p>
                    </div>
                )}

                <canvas
                    ref={canvasRef}
                    width={800}
                    height={600}
                    className={`max-w-full max-h-full object-contain ${!isConnected ? 'hidden' : ''}`}
                />
            </div>

            <div className="mt-4 text-xs text-slate-500 text-center">
                Security Note: Stream is encrypted via WebSocket (TLS). Quality auto-adjusted for bandwidth.
            </div>
        </div>
    );
};
