import React, { useEffect, useRef, useState } from 'react';
import { Terminal } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import 'xterm/css/xterm.css';
import { Agent } from '../types';
import { startRemoteSession } from '../services/apiService';

interface RemoteTerminalProps {
    agent: Agent;
    onClose: () => void;
}

export const RemoteTerminal: React.FC<RemoteTerminalProps> = ({ agent, onClose }) => {
    const terminalRef = useRef<HTMLDivElement>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const termRef = useRef<Terminal | null>(null);
    const fitRef = useRef<FitAddon | null>(null);
    const [connected, setConnected] = useState(false);

    useEffect(() => {
        if (!terminalRef.current) return;

        let cancelled = false;

        // ── 1. Initialise xterm ──────────────────────────────────────────────
        const terminal = new Terminal({
            cursorBlink: true,
            theme: { background: '#1e1e1e', foreground: '#f0f0f0' },
            fontFamily: 'Menlo, Monaco, "Courier New", monospace',
            fontSize: 14,
        });
        const fitAddon = new FitAddon();
        terminal.loadAddon(fitAddon);
        terminal.open(terminalRef.current);
        termRef.current = terminal;
        fitRef.current = fitAddon;

        // Defer fit() until after the browser has painted the flex container.
        // Calling it synchronously gives a 0×0 measurement and crashes xterm.
        const fitTimer = setTimeout(() => {
            if (!cancelled) {
                try { fitAddon.fit(); } catch { /* container not yet visible */ }
            }
        }, 60);

        // ── 2. WebSocket helpers ─────────────────────────────────────────────
        const connectWebSocket = (url: string) => {
            if (cancelled) return;

            const ws = new WebSocket(url);
            wsRef.current = ws;

            ws.onopen = () => {
                if (cancelled) { ws.close(); return; }
                setConnected(true);
                terminal.writeln('\x1b[32m✔ Secure Connection Established.\x1b[0m');
                terminal.writeln('Waiting for agent shell...\r\n');
                ws.send(JSON.stringify({ type: 'init', cols: terminal.cols, rows: terminal.rows }));
            };

            ws.onmessage = (event) => { terminal.write(event.data); };

            ws.onclose = () => {
                setConnected(false);
                if (!cancelled) terminal.writeln('\r\n\x1b[31m✖ Connection Closed.\x1b[0m');
            };

            ws.onerror = () => {
                if (!cancelled) terminal.writeln('\r\n\x1b[31m✖ WebSocket Error. Check that the backend is reachable.\x1b[0m');
            };

            terminal.onData((data) => {
                if (ws.readyState === WebSocket.OPEN) ws.send(data);
            });
        };

        // ── 3. Start remote session ──────────────────────────────────────────
        const startAgentSession = async () => {
            terminal.writeln(`\x1b[33mConnecting to ${agent.hostname} (${agent.ipAddress || 'unknown IP'})...\x1b[0m`);
            terminal.writeln('\x1b[34mRequesting agent connection...\x1b[0m');
            try {
                const response = await startRemoteSession(agent.id || agent.hostname, 'ssh', 'shell');
                if (cancelled) return;

                if (response?.session_id) {
                    terminal.writeln('\x1b[34mSession created. Connecting...\x1b[0m');
                    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                    const token = sessionStorage.getItem('token') || '';
                    const wsUrl = `${protocol}//${window.location.host}/api/tunnel/${response.session_id}/user?token=${encodeURIComponent(token)}`;
                    connectWebSocket(wsUrl);
                } else {
                    terminal.writeln('\x1b[31mFailed to start session: ' + (response?.error || 'Unknown error') + '\x1b[0m');
                }
            } catch (err) {
                if (!cancelled) terminal.writeln('\x1b[31mFailed to connect. Ensure the agent is online.\x1b[0m');
            }
        };

        startAgentSession();

        // ── 4. Resize handler ────────────────────────────────────────────────
        const handleResize = () => {
            try { fitAddon.fit(); } catch { /* terminal may be disposed */ }
        };
        window.addEventListener('resize', handleResize);

        // ── 5. Cleanup ───────────────────────────────────────────────────────
        return () => {
            cancelled = true;
            clearTimeout(fitTimer);
            window.removeEventListener('resize', handleResize);
            if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
                wsRef.current.close();
            }
            wsRef.current = null;
            try { terminal.dispose(); } catch { /* already disposed */ }
            termRef.current = null;
            fitRef.current = null;
        };
    }, [agent]);

    return (
        <div className="h-full w-full flex flex-col bg-black">
            <div className="bg-[#1e1e1e] w-full h-full flex flex-col border border-gray-700 rounded-lg shadow-2xl">
                {/* Header */}
                <div className="flex items-center justify-between px-4 py-2 bg-[#2d2d2d] border-b border-gray-700 rounded-t-lg shrink-0">
                    <div className="flex items-center gap-2">
                        <div className={`w-3 h-3 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500 animate-pulse'}`} />
                        <span className="text-gray-200 font-mono text-sm">
                            {connected ? `root@${agent.hostname}:~` : `Connecting to ${agent.hostname}…`}
                        </span>
                    </div>
                    <button onClick={onClose} className="text-gray-400 hover:text-white transition-colors text-lg leading-none">✕</button>
                </div>

                {/* xterm container — must have explicit height for fitAddon to measure */}
                <div className="flex-1 overflow-hidden p-1" ref={terminalRef} style={{ minHeight: 0 }} />
            </div>
        </div>
    );
};
