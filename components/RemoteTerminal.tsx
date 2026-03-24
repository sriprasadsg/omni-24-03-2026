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
    const [connected, setConnected] = useState(false);
    const term = useRef<Terminal | null>(null);

    useEffect(() => {
        if (!terminalRef.current) return;

        // Initialize xterm
        const terminal = new Terminal({
            cursorBlink: true,
            theme: {
                background: '#1e1e1e',
                foreground: '#f0f0f0',
            },
            fontFamily: 'Menlo, Monaco, "Courier New", monospace',
            fontSize: 14
        });

        const fitAddon = new FitAddon();
        terminal.loadAddon(fitAddon);
        terminal.open(terminalRef.current);
        fitAddon.fit();

        term.current = terminal;

        // Connect WebSocket (User Side)
        const connectWebSocket = (url: string) => {
            const ws = new WebSocket(url);
            wsRef.current = ws;

            ws.onopen = () => {
                setConnected(true);
                term.current?.writeln('\x1b[32m✔ Secure Connection Established.\x1b[0m');
                term.current?.writeln('Waiting for agent shell...\r\n');
                // Sending a ping or init command
                ws.send(JSON.stringify({ type: 'init', cols: term.current?.cols, rows: term.current?.rows }));
            };

            ws.onmessage = (event) => {
                term.current?.write(event.data);
            };

            ws.onclose = () => {
                setConnected(false);
                term.current?.writeln('\r\n\x1b[31m✖ Connection Closed.\x1b[0m');
            };

            ws.onerror = (err) => {
                console.error(err);
                term.current?.writeln('\r\n\x1b[31m✖ WebSocket Error.\x1b[0m');
            };

            // User Input -> WebSocket
            term.current?.onData((data) => {
                if (ws.readyState === WebSocket.OPEN) {
                    ws.send(data);
                }
            });
        };

        terminal.writeln(`\x1b[33mConnecting to ${agent.hostname} (${agent.ipAddress})...\x1b[0m`);

        // Trigger Agent Connection
        const startAgentSession = async () => {
            try {
                terminal.writeln('\x1b[34mRequesting agent connection...\x1b[0m');
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

                // Use agent.id if available, otherwise hostname
                const response = await startRemoteSession(agent.id || agent.hostname, 'ssh', 'shell');

                if (response.session_id) {
                    terminal.writeln('\x1b[34mSession created. Connecting...\x1b[0m');

                    let wsUrl = response.websocket_url;
                    if (wsUrl && wsUrl.includes("localhost:5000")) {
                        wsUrl = `${protocol}//${window.location.hostname}:5000/api/tunnel/${response.session_id}/user`;
                    }

                    connectWebSocket(wsUrl);
                } else {
                    terminal.writeln('\x1b[31mFailed to start session: ' + (response.error || 'Unknown error') + '\x1b[0m');
                }
            } catch (err) {
                console.error("Failed to start agent session", err);
                terminal.writeln('\x1b[31mFailed to trigger agent connection. Ensure agent is online.\x1b[0m');
            }
        };
        startAgentSession();

        // Resize handler
        const handleResize = () => fitAddon.fit();
        window.addEventListener('resize', handleResize);

        return () => {
            if (wsRef.current) {
                wsRef.current.close();
            }
            terminal.dispose();
            window.removeEventListener('resize', handleResize);
        };
    }, [agent]);

    return (
        <div className="fixed inset-0 bg-black bg-opacity-75 z-50 flex items-center justify-center p-4">
            <div className="bg-[#1e1e1e] rounded-lg shadow-2xl w-full max-w-5xl h-[80vh] flex flex-col border border-gray-700">
                {/* Header */}
                <div className="flex items-center justify-between px-4 py-2 bg-[#2d2d2d] border-b border-gray-700 rounded-t-lg">
                    <div className="flex items-center">
                        <div className={`w-3 h-3 rounded-full mr-2 ${connected ? 'bg-green-500' : 'bg-red-500'}`}></div>
                        <span className="text-gray-200 font-mono text-sm">root@{agent.hostname}:~</span>
                    </div>
                    <button
                        onClick={onClose}
                        className="text-gray-400 hover:text-white transition-colors"
                    >
                        ✕
                    </button>
                </div>

                {/* Terminal Container */}
                <div className="flex-grow overflow-hidden p-2" ref={terminalRef}></div>
            </div>
        </div>
    );
};
