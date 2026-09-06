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

/** Validate a single credential field: non-empty, no control chars, max 128 bytes. */
const validateCredential = (v: string): boolean => {
    if (!v || v.length > 128) return false;
    // Reject control characters (0x00-0x1F, 0x7F) except common whitespace
    // Allow tabs/newlines only if intentional (user may paste). Strip and re-check.
    return /^[\x20-\x7E -ɏ]+$/.test(v);
};

export const RemoteTerminal: React.FC<RemoteTerminalProps> = ({ agent, onClose }) => {
    const terminalRef = useRef<HTMLDivElement>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const termRef = useRef<Terminal | null>(null);
    const fitRef = useRef<FitAddon | null>(null);
    const [connected, setConnected] = useState(false);

    // Linux credential prompt state
    const isLinux = agent.platform === 'Linux';
    const [showCreds, setShowCreds] = useState(isLinux);
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [credError, setCredError] = useState('');

    // Store credentials after submit so the useEffect can read them
    const credsRef = useRef<{username: string; password: string} | null>(null);

    const submitCredentials = () => {
        const u = username.trim();
        const p = password;
        if (!validateCredential(u)) {
            setCredError('Username: non-empty, max 128 chars, no control characters.');
            return;
        }
        if (!validateCredential(p)) {
            setCredError('Password: non-empty, max 128 chars, no control characters.');
            return;
        }
        credsRef.current = { username: u, password: p };
        setShowCreds(false);
        setCredError('');
    };

    useEffect(() => {
        if (showCreds) return; // don't connect until creds submitted

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
                const creds = credsRef.current;
                const extra = (creds && isLinux) ? { username: creds.username, password: creds.password } : undefined;
                const response = await startRemoteSession(agent.id || agent.hostname, 'ssh', 'shell', extra);
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
    }, [agent, showCreds]);

    // Linux credential prompt — shown before connecting
    if (showCreds) {
        return (
            <div className="h-full w-full flex flex-col bg-[#1a1a2e] rounded-lg border border-gray-700">
                <div className="flex items-center justify-between px-4 py-3 bg-[#2d2d2d] border-b border-gray-700 rounded-t-lg">
                    <span className="text-gray-200 font-mono text-sm">SSH Credentials — {agent.hostname}</span>
                    <button onClick={onClose} className="text-gray-400 hover:text-white transition-colors text-lg leading-none">✕</button>
                </div>
                <div className="flex-1 flex items-center justify-center p-6">
                    <div className="w-full max-w-sm space-y-4">
                        <div>
                            <label className="block text-xs text-gray-400 mb-1">Username</label>
                            <input
                                type="text"
                                value={username}
                                onChange={(e) => { setUsername(e.target.value); setCredError(''); }}
                                onKeyDown={(e) => { if (e.key === 'Enter') submitCredentials(); }}
                                autoFocus
                                maxLength={128}
                                className="w-full bg-[#1e1e1e] border border-gray-600 rounded px-3 py-2 text-sm text-gray-100 font-mono focus:outline-none focus:border-blue-500"
                                placeholder="e.g. root"
                            />
                        </div>
                        <div>
                            <label className="block text-xs text-gray-400 mb-1">Password</label>
                            <input
                                type="password"
                                value={password}
                                onChange={(e) => { setPassword(e.target.value); setCredError(''); }}
                                onKeyDown={(e) => { if (e.key === 'Enter') submitCredentials(); }}
                                maxLength={128}
                                className="w-full bg-[#1e1e1e] border border-gray-600 rounded px-3 py-2 text-sm text-gray-100 font-mono focus:outline-none focus:border-blue-500"
                                placeholder="••••••"
                            />
                        </div>
                        {credError && (
                            <p className="text-red-400 text-xs">{credError}</p>
                        )}
                        <button
                            onClick={submitCredentials}
                            className="w-full bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold py-2 rounded transition-colors"
                        >
                            Connect
                        </button>
                        <p className="text-gray-500 text-xs text-center">Credentials are sent over the encrypted tunnel and never logged.</p>
                    </div>
                </div>
            </div>
        );
    }

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
