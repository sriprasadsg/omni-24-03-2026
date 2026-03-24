import io, { Socket } from 'socket.io-client';

type EventCallback = (data: any) => void;

class SocketService {
    private socket: Socket | null = null;
    private listeners: Map<string, EventCallback[]> = new Map();
    private isConnected: boolean = false;

    /**
     * Connect to WebSocket server
     * @param tenantId - Tenant ID for this connection
     */
    connect(tenantId: string) {
        if (this.socket) {
            console.warn('[WebSocket] Socket already connected');
            return;
        }

        const token = localStorage.getItem('token');
        const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

        console.log(`[WebSocket] Connecting for tenant: ${tenantId}`);

        this.socket = io(API_BASE, {
            auth: {
                tenant_id: tenantId,
                token: token
            },
            transports: ['websocket', 'polling'], // Try WebSocket first, fallback to polling
            reconnection: true,
            reconnectionAttempts: 5,
            reconnectionDelay: 1000
        });

        // Connection events
        this.socket.on('connect', () => {
            console.log('[WebSocket] ✅ Connected');
            this.isConnected = true;
        });

        this.socket.on('connected', (data) => {
            console.log('[WebSocket] Received welcome:', data);
        });

        this.socket.on('disconnect', (reason) => {
            console.log('[WebSocket] Disconnected:', reason);
            this.isConnected = false;
        });

        this.socket.on('connect_error', (error) => {
            console.error('[WebSocket] Connection error:', error);
        });

        // Application events
        this.socket.on('notification', (data) => {
            console.log('[WebSocket] 📬 Notification:', data);
            this.emit('notification', data);
        });

        this.socket.on('agent_status_change', (data) => {
            console.log('[WebSocket] 🤖 Agent status change:', data);
            this.emit('agent_status_change', data);
        });

        this.socket.on('security_event', (data) => {
            console.log('[WebSocket] 🔒 Security event:', data);
            this.emit('security_event', data);
        });

        this.socket.on('compliance_alert', (data) => {
            console.log('[WebSocket] ⚖️ Compliance alert:', data);
            this.emit('compliance_alert', data);
        });

        this.socket.on('pong', (data) => {
            console.log('[WebSocket] 🏓 Pong received:', data);
        });
    }

    /**
     * Disconnect from WebSocket server
     */
    disconnect() {
        if (this.socket) {
            console.log('[WebSocket] Disconnecting...');
            this.socket.disconnect();
            this.socket = null;
            this.isConnected = false;
            this.listeners.clear();
        }
    }

    /**
     * Subscribe to an event
     */
    on(event: string, callback: EventCallback) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, []);
        }
        this.listeners.get(event)!.push(callback);
    }

    /**
     * Unsubscribe from an event
     */
    off(event: string, callback: EventCallback) {
        const listeners = this.listeners.get(event);
        if (listeners) {
            const index = listeners.indexOf(callback);
            if (index > -1) {
                listeners.splice(index, 1);
            }
        }
    }

    /**
     * Emit event to local listeners
     */
    private emit(event: string, data: any) {
        const listeners = this.listeners.get(event);
        if (listeners) {
            listeners.forEach(callback => {
                try {
                    callback(data);
                } catch (error) {
                    console.error(`[WebSocket] Error in listener for ${event}:`, error);
                }
            });
        }
    }

    /**
     * Check if connected
     */
    get connected(): boolean {
        return this.isConnected;
    }

    /**
     * Send ping to test connection
     */
    ping() {
        if (this.socket) {
            this.socket.emit('ping');
            console.log('[WebSocket] Ping sent');
        }
    }
}

// Export singleton instance
export const socketService = new SocketService();
