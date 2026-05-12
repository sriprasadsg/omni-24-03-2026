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
        // Use Vite proxy (same-origin, no CORS issues) so socket.io goes through
        // http://host:3000/socket.io → proxy → http://127.0.0.1:5000/socket.io.
        // VITE_API_BASE_URL overrides this for production deployments.
        // Use current page origin so socket.io goes through Vite's /socket.io proxy rule.
        // VITE_API_BASE_URL overrides this in production (e.g. behind a reverse proxy).
        const API_BASE: string = import.meta.env.VITE_API_BASE_URL || window.location.origin;

        console.log(`[WebSocket] Connecting for tenant: ${tenantId} via ${API_BASE}`);

        this.socket = io(API_BASE, {
            auth: {
                tenant_id: tenantId,
                token: token
            },
            // polling first: HTTP long-poll goes through Vite's proxy reliably,
            // establishes the session, then upgrades to WebSocket automatically.
            // Starting with 'websocket' causes Vite's proxy to fail the upgrade.
            transports: ['polling', 'websocket'],
            upgrade: true,
            reconnection: true,
            reconnectionAttempts: 5,
            reconnectionDelay: 3000,
            timeout: 10000
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
            console.warn('[WebSocket] Connection error:', error.message);
        });

        this.socket.on('reconnect_failed', () => {
            console.warn('[WebSocket] All reconnection attempts failed. Real-time updates disabled. Is the backend running with socket_app?');
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
