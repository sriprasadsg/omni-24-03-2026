import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Activity, Zap, Shield, FileText, Wifi } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line } from 'recharts';

interface StreamEvent {
    type?: string; // from system_stats
    stats?: Record<string, number>; // from system_stats
    timestamp: string;
    [key: string]: any;
}

export function StreamingDashboard() {
    const [isConnected, setIsConnected] = useState(false);
    const [events, setEvents] = useState<StreamEvent[]>([]);
    const [metrics, setMetrics] = useState<any[]>([]);
    const wsRef = useRef<WebSocket | null>(null);

    // Stats for the chart
    const [chartData, setChartData] = useState<any[]>([]);

    useEffect(() => {
        // Connect to WebSocket
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/api/stream/live`;
        // For local dev with different port if needed, but proxy should handle it. 
        // Assuming backend on same origin or proxy forwarding.
        // If pure local dev split: ws://localhost:5000/api/stream/live

        // Fallback for localhost dev where frontend is 3000 and backend is 5000
        const finalUrl = window.location.hostname === 'localhost' ? 'ws://localhost:5000/api/stream/live' : wsUrl;

        const ws = new WebSocket(finalUrl);
        wsRef.current = ws;

        ws.onopen = () => {
            setIsConnected(true);
            console.log("Connected to Stream Processing Engine");
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleMessage(data);
            } catch (e) {
                console.error("Failed to parse websocket message", e);
            }
        };

        ws.onclose = () => {
            setIsConnected(false);
        };

        return () => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.close();
            }
        };
    }, []);

    const handleMessage = (data: StreamEvent) => {
        // If it's a stats update
        if (data.type === 'window_stats' && data.stats) {
            setChartData(prev => {
                const newData = [...prev, {
                    time: new Date(data.timestamp).toLocaleTimeString(),
                    logs: data.stats.logs_last_10s || 0,
                    threats: data.stats.threats_last_10s || 0
                }];
                return newData.slice(-20); // Keep last 20 points
            });
        } else {
            // It's a raw event (log or security)
            setEvents(prev => [data, ...prev].slice(0, 50)); // Keep last 50 events
        }
    };

    return (
        <div className="space-y-6 pt-6 pb-10 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent">
                        Real-Time Streaming Analytics
                    </h2>
                    <p className="text-muted-foreground mt-1">
                        Live event processing engine (Simulated Flink/Spark)
                    </p>
                </div>
                <Badge variant={isConnected ? "default" : "destructive"} className={isConnected ? "bg-green-500/20 text-green-400 hover:bg-green-500/30" : ""}>
                    {isConnected ? <Wifi className="mr-2 h-3 w-3" /> : <Wifi className="mr-2 h-3 w-3" />}
                    {isConnected ? "Live Stream Connected" : "Disconnected"}
                </Badge>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
                {/* Real-time Chart */}
                <Card className="col-span-2 glass-card border-slate-700/50">
                    <CardHeader>
                        <CardTitle>Event Velocity (10s Window)</CardTitle>
                        <CardDescription>Events processed per second (Rolling Window)</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="h-[300px] w-full">
                            <ResponsiveContainer width="100%" height="100%">
                                <LineChart data={chartData}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
                                    <XAxis dataKey="time" stroke="#94a3b8" fontSize={12} tickLine={false} axisLine={false} />
                                    <YAxis stroke="#94a3b8" fontSize={12} tickLine={false} axisLine={false} />
                                    <Tooltip
                                        contentStyle={{ backgroundColor: '#1e293b', borderColor: '#334155', borderRadius: '8px' }}
                                        itemStyle={{ color: '#e2e8f0' }}
                                    />
                                    <Line type="monotone" dataKey="logs" stroke="#3b82f6" strokeWidth={2} dot={false} activeDot={{ r: 4 }} name="Logs/sec" />
                                    <Line type="monotone" dataKey="threats" stroke="#ef4444" strokeWidth={2} dot={false} activeDot={{ r: 4 }} name="Threats/sec" />
                                </LineChart>
                            </ResponsiveContainer>
                        </div>
                    </CardContent>
                </Card>

                {/* Live Feed */}
                <Card className="col-span-1 glass-card border-slate-700/50">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Zap className="h-4 w-4 text-yellow-400" />
                            Live Feed
                        </CardTitle>
                        <CardDescription>Recent raw events</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-3 max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
                            {events.length === 0 ? (
                                <div className="text-center py-8 text-muted-foreground text-xs">Waiting for events...</div>
                            ) : (
                                events.map((evt, i) => (
                                    <div key={i} className="flex items-start gap-3 p-2 rounded bg-slate-800/20 border border-slate-700/30 text-xs">
                                        {evt.level === 'error' || evt.severity === 'high' ? (
                                            <Shield className="h-3 w-3 text-red-400 mt-0.5" />
                                        ) : (
                                            <FileText className="h-3 w-3 text-blue-400 mt-0.5" />
                                        )}
                                        <div className="flex-1 overflow-hidden">
                                            <div className="flex justify-between">
                                                <span className="font-semibold text-slate-300">{evt.source || 'System'}</span>
                                                <span className="text-slate-500 text-[10px]">{new Date(evt.timestamp).toLocaleTimeString()}</span>
                                            </div>
                                            <div className="text-slate-400 truncate">{evt.message || JSON.stringify(evt)}</div>
                                        </div>
                                    </div>
                                ))
                            )}
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
