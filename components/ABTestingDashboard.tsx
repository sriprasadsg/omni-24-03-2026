import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Plus, Beaker, Users, Target, TrendingUp } from 'lucide-react';
import { apiService } from '../services/apiService';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, ReferenceLine } from 'recharts';

interface Experiment {
    id: string;
    name: string;
    status: string;
    stats: Record<string, { impressions: number; conversions: number }>;
}

export function ABTestingDashboard() {
    const [experiments, setExperiments] = useState<Experiment[]>([]);
    const [selectedExpId, setSelectedExpId] = useState<string | null>(null);
    const [results, setResults] = useState<any>(null);
    const [demoUserId, setDemoUserId] = useState(`user-${Math.floor(Math.random() * 1000)}`);
    const [assignedVariant, setAssignedVariant] = useState<string | null>(null);

    useEffect(() => {
        fetchExperiments();
    }, []);

    useEffect(() => {
        if (selectedExpId) {
            fetchResults(selectedExpId);
            // Also check assignment for current demo user
            checkAssignment(selectedExpId, demoUserId);
            const interval = setInterval(() => fetchResults(selectedExpId), 2000);
            return () => clearInterval(interval);
        }
    }, [selectedExpId, demoUserId]);

    const fetchExperiments = async () => {
        try {
            const res = await apiService.get('/api/experiments/');
            setExperiments(res);
            if (!selectedExpId && res.length > 0) {
                setSelectedExpId(res[0].id);
            }
        } catch (error) {
            console.error("Failed to fetch experiments:", error);
        }
    };

    const fetchResults = async (id: string) => {
        try {
            const res = await apiService.get(`/api/experiments/${id}/results`);
            setResults(res);
        } catch (error) {
            console.error("Failed to fetch results:", error);
        }
    };

    const checkAssignment = async (expId: string, userId: string) => {
        try {
            const res = await apiService.get(`/api/experiments/${expId}/variant?user_id=${userId}`);
            setAssignedVariant(res.variant);
        } catch (error) {
            console.error("Failed to check assignment:", error);
        }
    };

    const createExperiment = async () => {
        try {
            const name = prompt("Enter Experiment Name (e.g. 'New Pricing Page'):");
            if (name) {
                await apiService.post('/api/experiments/', {
                    name,
                    description: "Demo Experiment",
                    variants: ["Control", "Treatment"]
                });
                fetchExperiments();
            }
        } catch (error) {
            console.error("Failed to create experiment:", error);
        }
    };

    const simulateConversion = async () => {
        if (!selectedExpId) return;
        try {
            await apiService.post(`/api/experiments/${selectedExpId}/track`, { user_id: demoUserId });
            // In a real app we wouldn't fetch results immediately as they might be async, but here it's instant
            fetchResults(selectedExpId);
        } catch (error) {
            console.error("Failed to track conversion:", error);
        }
    };

    const randomizeUser = () => {
        setDemoUserId(`user-${Math.floor(Math.random() * 10000)}`);
    };

    return (
        <div className="space-y-6 pt-6 pb-10 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-teal-400 to-green-400 bg-clip-text text-transparent">
                        Experimentation Platform
                    </h2>
                    <p className="text-muted-foreground mt-1">
                        A/B Testing & Feature Flag Management
                    </p>
                </div>
                <Button onClick={createExperiment} className="bg-gradient-to-r from-teal-600 to-green-600 hover:from-teal-700 hover:to-green-700">
                    <Plus className="mr-2 h-4 w-4" /> New Experiment
                </Button>
            </div>

            <div className="grid gap-6 md:grid-cols-3">
                {/* Experiments List */}
                <Card className="glass-card border-slate-700/50">
                    <CardHeader>
                        <CardTitle className="text-sm font-medium">Active Tests</CardTitle>
                    </CardHeader>
                    <CardContent className="p-0">
                        <div className="space-y-1">
                            {experiments.length === 0 && <div className="p-4 text-sm text-muted-foreground text-center">No experiments running.</div>}
                            {experiments.map(exp => (
                                <div
                                    key={exp.id}
                                    onClick={() => setSelectedExpId(exp.id)}
                                    className={`p-3 cursor-pointer transition-colors border-l-2 ${selectedExpId === exp.id ? 'bg-slate-800/50 border-teal-500' : 'hover:bg-slate-800/30 border-transparent'}`}
                                >
                                    <div className="font-medium text-slate-200">{exp.name}</div>
                                    <div className="flex justify-between text-xs text-muted-foreground mt-1">
                                        <Badge variant="outline" className="text-green-400 border-green-500/30 text-[10px] h-5">{exp.status}</Badge>
                                        <span className="flex items-center gap-1"><Users className="h-3 w-3" /> {Object.values(exp.stats).reduce<number>((a, b: { impressions: number }) => a + b.impressions, 0)}</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>

                {/* Results & Simulator */}
                <div className="col-span-2 space-y-4">
                    {results ? (
                        <>
                            {/* Simulator Box */}
                            <Card className="glass-card border-slate-700/50 bg-slate-900/50">
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                                        <Beaker className="h-4 w-4 text-teal-400" />
                                        Test Environment
                                    </CardTitle>
                                </CardHeader>
                                <CardContent className="flex items-center justify-between">
                                    <div className="space-y-1">
                                        <div className="text-xs text-muted-foreground">Current User ID</div>
                                        <div className="text-sm font-mono bg-slate-800 px-2 py-1 rounded border border-slate-700">{demoUserId}</div>
                                        <Button variant="link" size="sm" onClick={randomizeUser} className="text-teal-400 h-auto p-0 text-xs">Generate New User</Button>
                                    </div>
                                    <div className="text-center">
                                        <div className="text-xs text-muted-foreground mb-1">Assigned Variant</div>
                                        <Badge className={`text-lg px-3 py-1 ${assignedVariant === 'Control' ? 'bg-slate-700' : 'bg-teal-600'}`}>
                                            {assignedVariant || '...'}
                                        </Badge>
                                    </div>
                                    <Button onClick={simulateConversion} className="bg-green-600 hover:bg-green-700">
                                        <Target className="mr-2 h-4 w-4" /> Simulate Conversion
                                    </Button>
                                </CardContent>
                            </Card>

                            {/* Metrics Charts */}
                            <div className="grid md:grid-cols-2 gap-4">
                                <Card className="glass-card border-slate-700/50">
                                    <CardHeader>
                                        <CardTitle className="text-sm">Conversion Rate Comparison</CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        <div className="h-[200px] w-full">
                                            <ResponsiveContainer width="100%" height="100%">
                                                <BarChart data={results.data}>
                                                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#334155" />
                                                    <XAxis dataKey="variant" stroke="#94a3b8" fontSize={12} />
                                                    <YAxis stroke="#94a3b8" fontSize={12} tickFormatter={(val) => `${(val * 100).toFixed(0)}%`} />
                                                    <Tooltip
                                                        cursor={{ fill: '#334155', opacity: 0.2 }}
                                                        contentStyle={{ backgroundColor: '#1e293b', borderColor: '#334155' }}
                                                        formatter={(val: number) => [`${(val * 100).toFixed(1)}%`, 'Conv. Rate']}
                                                    />
                                                    <Bar dataKey="conversion_rate" radius={[4, 4, 0, 0]}>
                                                        {results.data.map((entry: any, index: number) => (
                                                            <Cell key={`cell-${index}`} fill={entry.variant === 'Control' ? '#64748b' : '#14b8a6'} />
                                                        ))}
                                                    </Bar>
                                                </BarChart>
                                            </ResponsiveContainer>
                                        </div>
                                    </CardContent>
                                </Card>

                                <Card className="glass-card border-slate-700/50">
                                    <CardHeader>
                                        <CardTitle className="text-sm">Performance Lift</CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        <div className="space-y-4">
                                            {results.data.filter((d: any) => d.variant !== 'Control').map((d: any) => (
                                                <div key={d.variant} className="p-4 rounded-lg bg-slate-800/30 border border-slate-700/50">
                                                    <div className="flex justify-between items-start mb-2">
                                                        <span className="font-bold text-slate-200">{d.variant} vs Control</span>
                                                        {d.statistically_significant ? (
                                                            <Badge className="bg-green-500/20 text-green-400 border-green-500/30">Significant</Badge>
                                                        ) : (
                                                            <Badge variant="outline" className="text-slate-500 border-slate-700">Not Significant</Badge>
                                                        )}
                                                    </div>
                                                    <div className="text-3xl font-bold text-teal-400">
                                                        {d.lift > 0 ? '+' : ''}{(d.lift * 100).toFixed(2)}%
                                                    </div>
                                                    <div className="text-xs text-muted-foreground mt-1">
                                                        Uplift in conversion rate
                                                    </div>
                                                </div>
                                            ))}
                                            {results.data.length <= 1 && (
                                                <div className="text-center text-muted-foreground text-sm py-8">Need more variants data.</div>
                                            )}
                                        </div>
                                    </CardContent>
                                </Card>
                            </div>
                        </>
                    ) : (
                        <div className="h-full flex items-center justify-center text-muted-foreground border-2 border-dashed border-slate-700/50 rounded-lg">
                            Select an experiment to view results.
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
