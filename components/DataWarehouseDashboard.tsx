import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Loader2, Database, Activity, Server, RefreshCw, Layers, HardDrive } from 'lucide-react';
import { authFetch } from '../services/apiService';
const apiService = {
    get: (url: string) => authFetch(url).then(r => r.ok ? r.json() : null),
    post: (url: string, data?: any) => authFetch(url, { method: 'POST', body: JSON.stringify(data) }).then(r => r.ok ? r.json() : null),
};
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

interface WarehouseStats {
    total_threats_processed: number;
    total_api_calls_analyzed: number;
    warehouse_status: string;
}

interface ETLJob {
    id: string;
    job_id: string;
    start_time: string;
    end_time: string;
    status: string;
    details: string[];
}

// Runs per day for the last 7 days (local dates), oldest first
export const etlRunsByDay = (jobs: { start_time: string }[], now = new Date()) => {
    const days = Array.from({ length: 7 }, (_, i) => {
        const d = new Date(now);
        d.setDate(d.getDate() - (6 - i));
        return { key: d.toDateString(), name: d.toLocaleDateString(undefined, { weekday: 'short' }), runs: 0 };
    });
    for (const job of jobs) {
        const t = new Date(job.start_time);
        const day = days.find(d => d.key === t.toDateString());
        if (day) day.runs += 1;
    }
    return days.map(({ name, runs }) => ({ name, runs }));
};

export function DataWarehouseDashboard() {
    const [stats, setStats] = useState<WarehouseStats | null>(null);
    const [history, setHistory] = useState<ETLJob[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [isRunningEtl, setIsRunningEtl] = useState(false);

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 30000); // Poll every 30s
        return () => clearInterval(interval);
    }, []);

    const fetchData = async () => {
        setIsLoading(true);
        try {
            const [statsRes, historyRes] = await Promise.all([
                apiService.get('/api/warehouse/stats'),
                apiService.get('/api/etl/history')
            ]);
            setStats(statsRes);
            setHistory(Array.isArray(historyRes) ? historyRes : []);
        } catch (error) {
            console.error("Failed to fetch warehouse data:", error);
        } finally {
            setIsLoading(false);
        }
    };

    const runEtlJob = async () => {
        setIsRunningEtl(true);
        try {
            await apiService.post('/api/etl/run', {});
            // Refresh history after a short delay
            setTimeout(fetchData, 2000);
        } catch (error) {
            console.error("Failed to trigger ETL:", error);
        } finally {
            setIsRunningEtl(false);
        }
    };

    return (
        <div className="space-y-6 pt-6 pb-10 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent">
                        Data Warehouse
                    </h2>
                    <p className="text-muted-foreground mt-1">
                        Centralized analytics and ETL pipeline management
                    </p>
                </div>
                <div className="flex gap-2">
                    <Button variant="outline" onClick={fetchData} disabled={isLoading} className="border-slate-700 hover:bg-slate-800">
                        <RefreshCw className={`mr-2 h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
                        Refresh
                    </Button>
                    <Button onClick={runEtlJob} disabled={isRunningEtl} className="bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-700 hover:to-cyan-700 card-shadow-glow">
                        {isRunningEtl ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Database className="mr-2 h-4 w-4" />}
                        Trigger ETL Job
                    </Button>
                </div>
            </div>

            {/* Stats Cards */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <Card className="glass-card border-slate-700/50">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Warehouse Status</CardTitle>
                        <Server className="h-4 w-4 text-green-400" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold capitalize text-green-400">{stats?.warehouse_status || 'Unknown'}</div>
                        <p className="text-xs text-muted-foreground">MongoDB Analytics Collections</p>
                    </CardContent>
                </Card>

                <Card className="glass-card border-slate-700/50">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Threats Processed</CardTitle>
                        <Activity className="h-4 w-4 text-red-400" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{stats?.total_threats_processed?.toLocaleString() || 0}</div>
                        <p className="text-xs text-muted-foreground">Aggregated events</p>
                    </CardContent>
                </Card>

                <Card className="glass-card border-slate-700/50">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">API Analytics</CardTitle>
                        <Layers className="h-4 w-4 text-blue-400" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{stats?.total_api_calls_analyzed?.toLocaleString() || 0}</div>
                        <p className="text-xs text-muted-foreground">Total API calls tracked</p>
                    </CardContent>
                </Card>

                <Card className="glass-card border-slate-700/50">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Last ETL Run</CardTitle>
                        <HardDrive className="h-4 w-4 text-purple-400" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">
                            {history.length > 0 ? new Date(history[0].end_time).toLocaleTimeString() : 'Never'}
                        </div>
                        <p className="text-xs text-muted-foreground">
                            {history.length > 0 ? history[0].status : 'N/A'}
                        </p>
                    </CardContent>
                </Card>
            </div>

            <div className="grid gap-4 md:grid-cols-7">
                {/* ETL History */}
                <Card className="col-span-4 glass-card border-slate-700/50">
                    <CardHeader>
                        <CardTitle>ETL Pipeline History</CardTitle>
                        <CardDescription>Recent extraction and transformation jobs</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-4 max-h-[400px] overflow-y-auto pr-2 custom-scrollbar">
                            {history.length === 0 ? (
                                <div className="text-center py-8 text-muted-foreground">No ETL jobs found. Trigger one to get started.</div>
                            ) : (
                                history.map((job) => (
                                    <div key={job.id} className="flex items-center justify-between p-4 border border-slate-700/50 rounded-lg bg-slate-800/20 hover:bg-slate-800/40 transition-colors">
                                        <div className="flex items-center gap-4">
                                            <div className={`p-2 rounded-full ${job.status === 'success' ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                                                {job.status === 'success' ? <Activity className="h-4 w-4" /> : <Activity className="h-4 w-4" />}
                                            </div>
                                            <div>
                                                <p className="font-medium text-sm">{job.job_id}</p>
                                                <p className="text-xs text-muted-foreground">
                                                    {new Date(job.start_time).toLocaleString()}
                                                </p>
                                            </div>
                                        </div>
                                        <div className="text-right">
                                            <Badge variant={job.status === 'success' ? 'default' : 'destructive'} className={job.status === 'success' ? 'bg-green-500/20 text-green-400 hover:bg-green-500/30' : ''}>
                                                {job.status}
                                            </Badge>
                                            <p className="text-xs text-muted-foreground mt-1">{job.details.length} steps</p>
                                        </div>
                                    </div>
                                ))
                            )}

                        </div>
                    </CardContent>
                </Card>

                {/* ETL activity per day, from the job history */}
                <Card className="col-span-3 glass-card border-slate-700/50">
                    <CardHeader>
                        <CardTitle>ETL Runs (last 7 days)</CardTitle>
                        <CardDescription>{history.length ? 'Pipeline runs per day' : 'No ETL runs yet — trigger one to start'}</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="h-[300px] w-full mt-4">
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={etlRunsByDay(history)}>
                                    <defs>
                                        <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                                            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
                                    <XAxis dataKey="name" stroke="#94a3b8" fontSize={12} tickLine={false} axisLine={false} />
                                    <YAxis stroke="#94a3b8" fontSize={12} tickLine={false} axisLine={false} allowDecimals={false} />
                                    <Tooltip
                                        contentStyle={{ backgroundColor: '#1e293b', borderColor: '#334155', borderRadius: '8px' }}
                                        itemStyle={{ color: '#e2e8f0' }}
                                    />
                                    <Area type="monotone" dataKey="runs" name="Runs" stroke="#3b82f6" strokeWidth={2} fillOpacity={1} fill="url(#colorValue)" />
                                </AreaChart>
                            </ResponsiveContainer>
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
