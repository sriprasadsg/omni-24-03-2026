/**
 * Frontend WebSocket Hook
 * React hook for WebSocket real-time updates
 */

import { useState, useEffect, useCallback, useRef } from 'react';

export interface WebSocketMessage {
    type: string;
    data: any;
    timestamp: string;
}

export interface UseWebSocketOptions {
    url: string;
    autoConnect?: boolean;
    reconnectInterval?: number;
    maxReconnectAttempts?: number;
    onMessage?: (message: WebSocketMessage) => void;
    onConnect?: () => void;
    onDisconnect?: () => void;
    onError?: (error: any) => void;
}

export function useWebSocket(options: UseWebSocketOptions) {
    const {
        url,
        autoConnect = true,
        reconnectInterval = 5000,
        maxReconnectAttempts = 10,
        onMessage,
        onConnect,
        onDisconnect,
        onError
    } = options;

    const [isConnected, setIsConnected] = useState(false);
    const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
    const [connectionStatus, setConnectionStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected');

    const wsRef = useRef<WebSocket | null>(null);
    const reconnectAttemptsRef = useRef(0);
    const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

    const connect = useCallback(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            return; // Already connected
        }

        setConnectionStatus('connecting');

        try {
            const ws = new WebSocket(url);

            ws.onopen = () => {
                console.log('[WebSocket] Connected to', url);
                setIsConnected(true);
                setConnectionStatus('connected');
                reconnectAttemptsRef.current = 0;
                onConnect?.();
            };

            ws.onmessage = (event) => {
                try {
                    const message: WebSocketMessage = JSON.parse(event.data);
                    setLastMessage(message);
                    onMessage?.(message);
                } catch (error) {
                    console.error('[WebSocket] Failed to parse message:', error);
                }
            };

            ws.onclose = () => {
                console.log('[WebSocket] Disconnected');
                setIsConnected(false);
                setConnectionStatus('disconnected');
                wsRef.current = null;
                onDisconnect?.();

                // Attempt reconnection
                if (reconnectAttemptsRef.current < maxReconnectAttempts) {
                    reconnectAttemptsRef.current++;
                    console.log(`[WebSocket] Reconnecting... (attempt ${reconnectAttemptsRef.current}/${maxReconnectAttempts})`);

                    reconnectTimeoutRef.current = setTimeout(() => {
                        connect();
                    }, reconnectInterval);
                } else {
                    console.error('[WebSocket] Max reconnection attempts reached');
                }
            };

            ws.onerror = (error) => {
                console.error('[WebSocket] Error:', error);
                onError?.(error);
            };

            wsRef.current = ws;
        } catch (error) {
            console.error('[WebSocket] Connection error:', error);
            setConnectionStatus('disconnected');
        }
    }, [url, reconnectInterval, maxReconnectAttempts, onConnect, onMessage, onDisconnect, onError]);

    const disconnect = useCallback(() => {
        if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
            reconnectTimeoutRef.current = null;
        }

        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }

        reconnectAttemptsRef.current = maxReconnectAttempts; // Prevent auto-reconnect
        setIsConnected(false);
        setConnectionStatus('disconnected');
    }, [maxReconnectAttempts]);

    const send = useCallback((data: any) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            const message = typeof data === 'string' ? data : JSON.stringify(data);
            wsRef.current.send(message);
            return true;
        } else {
            console.warn('[WebSocket] Cannot send message: not connected');
            return false;
        }
    }, []);

    useEffect(() => {
        if (autoConnect) {
            connect();
        }

        return () => {
            disconnect();
        };
    }, [autoConnect, connect, disconnect]);

    return {
        isConnected,
        connectionStatus,
        lastMessage,
        connect,
        disconnect,
        send
    };
}

export default useWebSocket;
