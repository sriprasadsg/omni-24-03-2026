import React, { useState, useEffect, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DollarSign, TrendingUp, PieChart, ArrowDownRight, CheckCircle } from 'lucide-react';
import { authFetch } from '../services/apiService';
import {
    ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip,
    ResponsiveContainer, BarChart, Bar, Cell, ReferenceLine
} from 'recharts';
import { Progress } from "@/components/ui/progress";

interface CostData {
    snapshot: {
        total_spend: number;
        breakdown: { compute: number; storage: number; network: number };
        budget_usage_percent: number;
    };
    history: { date: string; cost: number }[];
    forecast: { forecast_total: number; budget: number; status: string };
}

interface Recommendation {
    id: string;
    type: string;
    severity: string;
    description: string;
    potential_savings: number;
    action: string;
}

const BREAKDOWN_COLORS: Record<string, string> = {
    compute: '#8b5cf6',
    storage: '#3b82f6',
    network: '#10b981',
};

export function FinOpsDashboard() {
    const [data, setData] = useState<CostData | null>(null);
    const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
    const [isLoading, setIsLoading] = useState(false);

    useEffect(() => { fetchData(); }, []);

    const fetchData = async () => {
        setIsLoading(true);
        try {
            const [costRes, recRes] = await Promise.all([
                authFetch('/api/finops/costs').then(r => r.ok ? r.json() : null),
                authFetch('/api/finops/recommendations').then(r => r.ok ? r.json() : []),
            ]);
            if (costRes) setData(costRes);
            setRecommendations(Array.isArray(recRes) ? recRes : []);
        } catch (error) {
            console.error("Failed to fetch FinOps data:", error);
        } finally {
            setIsLoading(false);
        }
    };

    // Build combined history + forecast series for the chart
    const chartData = useMemo(() => {
        if (!data?.history) return [];
        const history = data.history;
        const today = new Date().toISOString().slice(0, 10);
        const todayIdx = history.findIndex(h => h.date >= today);

        // Compute average daily from actual non-zero days
        const actualDays = history.filter(h => h.date < today && h.cost > 0);
        const avgDaily = actualDays.length > 0
            ? actualDays.reduce((s, h) => s + h.cost, 0) / actualDays.length
            : (data.forecast?.forecast_total ?? 0) / 30;

        return history.map((h, i) => ({
            date: h.date.slice(5), // MM-DD
            cost: h.date <= today ? h.cost : undefined,
            forecast: i >= (todayIdx >= 0 ? todayIdx : history.length - 1)
                ? Math.round(avgDaily * 100) / 100
                : undefined,
        }));
    }, [data]);

    const getSeverityColor = (severity: string) => {
        switch (severity) {
            case 'HIGH': return 'bg-red-500/10 text-red-400 border-red-500/20';
            case 'MEDIUM': return 'bg-orange-500/10 text-orange-400 border-orange-500/20';
            case 'LOW': return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
            default: return 'bg-gray-500/10 text-gray-400';
        }
    };

    const totalPossibleSavings = recommendations.reduce((acc, rec) => acc + rec.potential_savings, 0);
    const breakdownEntries = data?.snapshot.breakdown
        ? Object.entries(data.snapshot.breakdown).map(([k, v]) => ({ name: k, value: v }))
        : [];
    const isOverBudget = data?.forecast.status === 'OVER_BUDGET';
    const todayLabel = new Date().toISOString().slice(5, 10);

    return (
        <div className="space-y-6 pt-6 pb-10 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-emerald-400 to-teal-400 bg-clip-text text-transparent">
                        FinOps & Cost Optimization
                    </h2>
                    <p className="text-muted-foreground mt-1">Cloud spend tracking and optimization recommendations</p>
                </div>
                <Button onClick={fetchData} disabled={isLoading} variant="outline" className="border-slate-700 hover:bg-slate-800">
                    {isLoading ? 'Refreshing…' : 'Refresh Data'}
                </Button>
            </div>

            {/* Top Stats */}
            <div className="grid gap-4 md:grid-cols-4">
                <Card className="glass-card border-slate-700/50">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Month-to-Date Spend</CardTitle>
                        <DollarSign className="h-4 w-4 text-emerald-400" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-emerald-400">
                            ${data?.snapshot.total_spend.toLocaleString() || '0.00'}
                        </div>
                        <p className="text-xs text-muted-foreground mt-1">
                            Projected EOM: ${data?.forecast.forecast_total.toLocaleString() ?? '—'}
                        </p>
                    </CardContent>
                </Card>

                <Card className="glass-card border-slate-700/50">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Budget Usage</CardTitle>
                        <PieChart className="h-4 w-4 text-blue-400" />
                    </CardHeader>
                    <CardContent>
                        <div className="flex items-center justify-between mb-1">
                            <span className="text-2xl font-bold">{data?.snapshot.budget_usage_percent ?? 0}%</span>
                            <Badge variant="outline" className={isOverBudget ? 'bg-red-500/10 text-red-500' : 'bg-green-500/10 text-green-500'}>
                                {isOverBudget ? 'Over Budget' : 'On Track'}
                            </Badge>
                        </div>
                        <Progress value={data?.snapshot.budget_usage_percent || 0} className={`h-2 ${isOverBudget ? 'bg-red-900/20' : ''}`} />
                        {data?.forecast.budget && (
                            <p className="text-xs text-muted-foreground mt-1">
                                Budget: ${data.forecast.budget.toLocaleString()}
                            </p>
                        )}
                    </CardContent>
                </Card>

                <Card className="glass-card border-slate-700/50">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Potential Savings</CardTitle>
                        <ArrowDownRight className="h-4 w-4 text-emerald-400" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-emerald-400">${totalPossibleSavings.toLocaleString()}</div>
                        <p className="text-xs text-muted-foreground mt-1">{recommendations.length} opportunities found</p>
                    </CardContent>
                </Card>

                <Card className="glass-card border-slate-700/50">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Compute Cost</CardTitle>
                        <TrendingUp className="h-4 w-4 text-purple-400" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">${data?.snapshot.breakdown.compute.toLocaleString() || 0}</div>
                        <p className="text-xs text-muted-foreground">Largest cost center</p>
                    </CardContent>
                </Card>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
                {/* Cost Trend + Forecast Chart */}
                <Card className="col-span-2 glass-card border-slate-700/50">
                    <CardHeader>
                        <CardTitle>30-Day Cost Trend & Forecast</CardTitle>
                        <CardDescription className="flex items-center gap-4 mt-1">
                            <span className="flex items-center gap-1.5 text-xs">
                                <span className="inline-block w-6 h-0.5 bg-emerald-500" /> Actual spend
                            </span>
                            <span className="flex items-center gap-1.5 text-xs">
                                <span className="inline-block w-6 border-t-2 border-dashed border-amber-400" /> Projected
                            </span>
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="h-[300px] w-full mt-2">
                            <ResponsiveContainer width="100%" height="100%">
                                <ComposedChart data={chartData}>
                                    <defs>
                                        <linearGradient id="colorCost" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                                            <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
                                    <XAxis dataKey="date" stroke="#94a3b8" fontSize={11} tickLine={false} axisLine={false}
                                        interval={4} />
                                    <YAxis stroke="#94a3b8" fontSize={11} tickLine={false} axisLine={false}
                                        tickFormatter={v => `$${v}`} />
                                    <Tooltip
                                        contentStyle={{ backgroundColor: '#1e293b', borderColor: '#334155', borderRadius: '8px' }}
                                        formatter={(value: number, name: string) => [`$${value}`, name === 'cost' ? 'Actual' : 'Forecast']}
                                    />
                                    <ReferenceLine x={todayLabel} stroke="#64748b" strokeDasharray="3 3"
                                        label={{ value: 'Today', position: 'top', fontSize: 10, fill: '#94a3b8' }} />
                                    <Area type="monotone" dataKey="cost" stroke="#10b981" strokeWidth={2}
                                        fillOpacity={1} fill="url(#colorCost)" connectNulls={false} />
                                    <Line type="monotone" dataKey="forecast" stroke="#f59e0b" strokeWidth={1.5}
                                        strokeDasharray="6 3" dot={false} connectNulls={true} />
                                </ComposedChart>
                            </ResponsiveContainer>
                        </div>
                    </CardContent>
                </Card>

                {/* Recommendations */}
                <Card className="col-span-1 glass-card border-slate-700/50">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <CheckCircle className="h-5 w-5 text-emerald-400" /> Optimization Plan
                        </CardTitle>
                        <CardDescription>Actionable recommendations</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-4 max-h-[350px] overflow-y-auto pr-2">
                            {recommendations.length === 0 ? (
                                <div className="text-center py-8 text-muted-foreground">No recommendations available.</div>
                            ) : recommendations.map(rec => (
                                <div key={rec.id} className="p-3 rounded-lg border border-slate-700/50 bg-slate-800/20">
                                    <div className="flex justify-between items-start mb-2">
                                        <Badge variant="outline" className={getSeverityColor(rec.severity)}>{rec.type}</Badge>
                                        <span className="text-emerald-400 font-bold text-sm">+${rec.potential_savings}</span>
                                    </div>
                                    <p className="text-sm text-slate-300 font-medium mb-1">{rec.description}</p>
                                    <Button size="sm" variant="secondary" className="w-full mt-2 h-7 text-xs bg-slate-700 hover:bg-slate-600">
                                        {rec.action}
                                    </Button>
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Cost Breakdown bar chart */}
            {breakdownEntries.length > 0 && (
                <Card className="glass-card border-slate-700/50">
                    <CardHeader>
                        <CardTitle>Cost Breakdown by Category</CardTitle>
                        <CardDescription>Current month spend per service type</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="h-[200px]">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={breakdownEntries} layout="vertical">
                                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" horizontal={false} />
                                    <XAxis type="number" stroke="#94a3b8" fontSize={11} tickFormatter={v => `$${v}`} />
                                    <YAxis type="category" dataKey="name" stroke="#94a3b8" fontSize={11} width={70}
                                        tickFormatter={v => v.charAt(0).toUpperCase() + v.slice(1)} />
                                    <Tooltip
                                        contentStyle={{ backgroundColor: '#1e293b', borderColor: '#334155', borderRadius: '8px' }}
                                        formatter={(v: number) => [`$${v.toLocaleString()}`, 'Cost']}
                                    />
                                    <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                                        {breakdownEntries.map(entry => (
                                            <Cell key={entry.name} fill={BREAKDOWN_COLORS[entry.name] || '#6b7280'} />
                                        ))}
                                    </Bar>
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </CardContent>
                </Card>
            )}
        </div>
    );
}
