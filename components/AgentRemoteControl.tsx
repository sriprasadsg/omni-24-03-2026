import React, { useState, useEffect, useRef } from 'react';
import { Terminal, Power, X, Wifi, WifiOff } from 'lucide-react';
import { Agent } from '../types';

interface AgentRemoteControlProps {
    agent: Agent;
    onClose: () => void;
}

export default function AgentRemoteControl({ agent, onClose }: AgentRemoteControlProps) {
    const [ws, setWs] = useState<WebSocket | null>(null);
    const [commandHistory, setCommandHistory] = useState<string[]>([]);
    const [historyIndex, setHistoryIndex] = useState(-1);
    const [currentCommand, setCurrentCommand] = useState('');
    const [output, setOutput] = useState<Array<{ type: 'input' | 'output' | 'error' | 'system', text: string }>>([]);
    const [isConnected, setIsConnected] = useState(false);
    const terminalRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        // Get current user ID from localStorage
        const token = localStorage.getItem('token');
        if (!token) {
            setOutput([{ type: 'error', text: 'Not authenticated' }]);
            return;
        }

        // Decode JWT to get user email/ID
        const payload = JSON.parse(atob(token.split('.')[1]));
        const userId = payload.sub; // This is the email

        // Connect to WebSocket
        const websocket = new WebSocket(`ws://localhost:5000/api/agents/remote/ws/user/${userId}`);

        websocket.onopen = () => {
            setIsConnected(true);
            setOutput([{
                type: 'system',
                text: `╔════════════════════════════════════════════════════════╗
║     Omni Agent Remote Control Terminal v1.0          ║
╚════════════════════════════════════════════════════════╝

Connected to: ${agent.hostname}
Agent ID: ${agent.id}
Status: Online

Type 'help' for available commands
Type 'exit' to close this session
`
            }]);
        };

        websocket.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.type === 'command_result' && data.agent_id === agent.id) {
                const result = data.result;

                if (result.success) {
                    if (result.stdout && result.stdout.trim()) {
                        setOutput(prev => [...prev, { type: 'output', text: result.stdout }]);
                    }
                    if (result.stderr && result.stderr.trim()) {
                        setOutput(prev => [...prev, { type: 'error', text: result.stderr }]);
                    }
                    if (!result.stdout && !result.stderr) {
                        setOutput(prev => [...prev, { type: 'system', text: `Command executed successfully (no output)` }]);
                    }
                } else {
                    setOutput(prev => [...prev, {
                        type: 'error',
                        text: `Error: ${result.error || 'Command failed'}`
                    }]);
                }
            }
        };

        websocket.onclose = () => {
            setIsConnected(false);
            setOutput(prev => [...prev, {
                type: 'error',
                text: '\\n[Disconnected from server]'
            }]);
        };

        websocket.onerror = (error) => {
            setOutput(prev => [...prev, {
                type: 'error',
                text: `WebSocket error: ${error}`
            }]);
        };

        setWs(websocket);

        // Send ping every 30 seconds to keep connection alive
        const pingInterval = setInterval(() => {
            if (websocket.readyState === WebSocket.OPEN) {
                websocket.send('ping');
            }
        }, 30000);

        return () => {
            clearInterval(pingInterval);
            websocket.close();
        };
    }, [agent]);

    useEffect(() => {
        // Auto-scroll to bottom when output changes
        if (terminalRef.current) {
            terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
        }
    }, [output]);

    useEffect(() => {
        // Focus input when connected
        if (isConnected && inputRef.current) {
            inputRef.current.focus();
        }
    }, [isConnected]);

    const executeCommand = async () => {
        if (!currentCommand.trim() || !isConnected) return;

        const cmd = currentCommand.trim();

        // Add to output
        setOutput(prev => [...prev, {
            type: 'input',
            text: `$ ${cmd}`
        }]);

        // Handle built-in commands
        if (cmd === 'exit' || cmd === 'quit') {
            onClose();
            return;
        }

        if (cmd === 'help') {
            setOutput(prev => [...prev, {
                type: 'system',
                text: `
Available Commands:
  help              - Show this help message
  exit, quit        - Close remote session
  clear             - Clear terminal output  
  restart-agent     - Restart the agent process
  
Any other command will be executed on the remote agent.

Examples:
  whoami           - Show current user
  hostname         - Show hostname
  ipconfig         - Show network configuration (Windows)
  ifconfig         - Show network configuration (Linux)
  ps aux           - List running processes (Linux)
  tasklist         - List running processes (Windows)
`
            }]);
            setCommandHistory(prev => [...prev, cmd]);
            setCurrentCommand('');
            setHistoryIndex(-1);
            return;
        }

        if (cmd === 'clear') {
            setOutput([{
                type: 'system',
                text: `Terminal cleared. Connected to ${agent.hostname}`
            }]);
            setCommandHistory(prev => [...prev, cmd]);
            setCurrentCommand('');
            setHistoryIndex(-1);
            return;
        }

        if (cmd === 'restart-agent') {
            restartAgent();
            setCommandHistory(prev => [...prev, cmd]);
            setCurrentCommand('');
            setHistoryIndex(-1);
            return;
        }

        // Add to history
        setCommandHistory(prev => [...prev, cmd]);
        setHistoryIndex(-1);

        // Execute remote command
        try {
            const token = localStorage.getItem('token');
            const response = await fetch(`/api/agents/remote/${agent.id}/execute`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ command: cmd })
            });

            const data = await response.json();

            if (!data.success) {
                setOutput(prev => [...prev, {
                    type: 'error',
                    text: data.detail || 'Failed to send command to agent'
                }]);
            }
        } catch (error) {
            setOutput(prev => [...prev, {
                type: 'error',
                text: `Error: ${error}`
            }]);
        }

        setCurrentCommand('');
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') {
            executeCommand();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (commandHistory.length > 0) {
                const newIndex = historyIndex === -1
                    ? commandHistory.length - 1
                    : Math.max(0, historyIndex - 1);
                setHistoryIndex(newIndex);
                setCurrentCommand(commandHistory[newIndex]);
            }
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (historyIndex !== -1) {
                const newIndex = historyIndex + 1;
                if (newIndex >= commandHistory.length) {
                    setHistoryIndex(-1);
                    setCurrentCommand('');
                } else {
                    setHistoryIndex(newIndex);
                    setCurrentCommand(commandHistory[newIndex]);
                }
            }
        } else if (e.key === 'l' && e.ctrlKey) {
            e.preventDefault();
            setOutput([{
                type: 'system',
                text: `Terminal cleared. Connected to ${agent.hostname}`
            }]);
        }
    };

    const restartAgent = async () => {
        if (!confirm(`⚠️  Are you sure you want to restart agent "${agent.hostname}"?\n\nThe agent will disconnect and attempt to reconnect automatically.`)) {
            return;
        }

        try {
            const token = localStorage.getItem('token');
            const response = await fetch(`/api/agents/remote/${agent.id}/restart`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });

            const data = await response.json();
            if (data.success) {
                setOutput(prev => [...prev, {
                    type: 'system',
                    text: '🔄 Agent restart initiated. The agent will reconnect shortly...'
                }]);
            }
        } catch (error) {
            setOutput(prev => [...prev, {
                type: 'error',
                text: `Failed to restart agent: ${error}`
            }]);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 backdrop-blur-sm">
            <div className="bg-gray-900 rounded-lg shadow-2xl w-4/5 h-4/5 flex flex-col border border-gray-700">
                {/* Header */}
                <div className="p-3 border-b border-gray-700 flex justify-between items-center bg-gray-800">
                    <div className="flex items-center gap-3">
                        <Terminal size={20} className="text-green-400" />
                        <div>
                            <h2 className="text-lg font-bold text-white flex items-center gap-2">
                                Remote Terminal: {agent.hostname}
                                {isConnected ? (
                                    <Wifi size={16} className="text-green-400" title="Connected" />
                                ) : (
                                    <WifiOff size={16} className="text-red-400" title="Disconnected" />
                                )}
                            </h2>
                            <p className="text-xs text-gray-400">
                                {agent.ipAddress} | {agent.platform} | Agent ID: {agent.id}
                            </p>
                        </div>
                    </div>
                    <div className="flex gap-2">
                        <button
                            onClick={restartAgent}
                            className="px-3 py-1.5 bg-orange-600 text-white text-sm rounded hover:bg-orange-700 flex items-center gap-1"
                            disabled={!isConnected}
                        >
                            <Power size={14} />
                            Restart Agent
                        </button>
                        <button
                            onClick={onClose}
                            className="p-2 hover:bg-gray-700 rounded text-gray-400 hover:text-white"
                        >
                            <X size={20} />
                        </button>
                    </div>
                </div>

                {/* Terminal Output */}
                <div
                    ref={terminalRef}
                    className="flex-1 p-4 bg-black text-green-400 font-mono text-sm overflow-y-auto"
                    style={{ fontFamily: '"Courier New", Courier, monospace' }}
                >
                    {output.map((line, i) => (
                        <div
                            key={i}
                            className={`whitespace-pre-wrap mb-1 ${line.type === 'error' ? 'text-red-400' :
                                line.type === 'input' ? 'text-yellow-400 font-bold' :
                                    line.type === 'system' ? 'text-cyan-400' :
                                        'text-green-400'
                                }`}
                        >
                            {line.text}
                        </div>
                    ))}
                </div>

                {/* Command Input */}
                <div className="p-3 border-t border-gray-700 bg-gray-800 flex gap-2 items-center">
                    <span className="text-green-400 font-mono font-bold">$</span>
                    <input
                        ref={inputRef}
                        type="text"
                        value={currentCommand}
                        onChange={(e) => setCurrentCommand(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder={isConnected ? "Enter command..." : "Connecting..."}
                        className="flex-1 px-3 py-2 bg-black text-green-400 font-mono border border-gray-700 rounded focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                        disabled={!isConnected}
                        style={{ fontFamily: '"Courier New", Courier, monospace' }}
                    />
                    <button
                        onClick={executeCommand}
                        disabled={!isConnected || !currentCommand.trim()}
                        className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:bg-gray-600 disabled:cursor-not-allowed font-mono"
                    >
                        Execute
                    </button>
                </div>

                {/* Status Bar */}
                <div className="px-3 py-1 bg-gray-900 border-t border-gray-700 flex justify-between text-xs text-gray-500">
                    <span>History: {commandHistory.length} commands | Ctrl+L to clear</span>
                    <span>{isConnected ? '● Connected' : '○ Disconnected'}</span>
                </div>
            </div>
        </div>
    );
}
