import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DollarSign, TrendingUp, PieChart, ArrowDownRight, AlertCircle, CheckCircle } from 'lucide-react';
import { apiService } from '../services/apiService';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Cell } from 'recharts';
import { Progress } from "@/components/ui/progress";

interface CostData {
    snapshot: {
        total_spend: number;
        breakdown: {
            compute: number;
            storage: number;
            network: number;
        };
        budget_usage_percent: number;
    };
    history: { date: string; cost: number }[];
    forecast: {
        forecast_total: number;
        budget: number;
        status: string;
    };
}

interface Recommendation {
    id: string;
    type: string;
    severity: string;
    description: string;
    potential_savings: number;
    action: string;
}

export function FinOpsDashboard() {
    const [data, setData] = useState<CostData | null>(null);
    const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
    const [isLoading, setIsLoading] = useState(false);

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        setIsLoading(true);
        try {
            const [costRes, recRes] = await Promise.all([
                apiService.get('/api/finops/costs'),
                apiService.get('/api/finops/recommendations')
            ]);
            setData(costRes);
            setRecommendations(recRes);
        } catch (error) {
            console.error("Failed to fetch FinOps data:", error);
        } finally {
            setIsLoading(false);
        }
    };

    const getSeverityColor = (severity: string) => {
        switch (severity) {
            case 'HIGH': return 'bg-red-500/10 text-red-400 border-red-500/20';
            case 'MEDIUM': return 'bg-orange-500/10 text-orange-400 border-orange-500/20';
            case 'LOW': return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
            default: return 'bg-gray-500/10 text-gray-400';
        }
    };

    const totalPossibleSavings = recommendations.reduce((acc, rec) => acc + rec.potential_savings, 0);

    return (
        <div className="space-y-6 pt-6 pb-10 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-emerald-400 to-teal-400 bg-clip-text text-transparent">
                        FinOps & Cost Optimization
                    </h2>
                    <p className="text-muted-foreground mt-1">
                        Cloud spend tracking and optimization recommendations
                    </p>
                </div>
                <Button onClick={fetchData} variant="outline" className="border-slate-700 hover:bg-slate-800">
                    Refresh Data
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
                            Projected: ${data?.forecast.forecast_total.toLocaleString()}
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
                            <span className="text-2xl font-bold">{data?.snapshot.budget_usage_percent}%</span>
                            <Badge variant="outline" className={data?.forecast.status === 'OVER_BUDGET' ? 'bg-red-500/10 text-red-500' : 'bg-green-500/10 text-green-500'}>
                                {data?.forecast.status === 'OVER_BUDGET' ? 'Over Budget' : 'On Track'}
                            </Badge>
                        </div>
                        <Progress value={data?.snapshot.budget_usage_percent || 0} className={`h-2 ${data?.forecast.status === 'OVER_BUDGET' ? 'bg-red-900/20' : ''}`} />
                    </CardContent>
                </Card>

                <Card className="glass-card border-slate-700/50">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Potential Savings</CardTitle>
                        <ArrowDownRight className="h-4 w-4 text-emerald-400" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-emerald-400">
                            ${totalPossibleSavings.toLocaleString()}
                        </div>
                        <p className="text-xs text-muted-foreground mt-1">{recommendations.length} opportunities found</p>
                    </CardContent>
                </Card>

                <Card className="glass-card border-slate-700/50">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Compute Cost</CardTitle>
                        <TrendingUp className="h-4 w-4 text-purple-400" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">
                            ${data?.snapshot.breakdown.compute.toLocaleString() || 0}
                        </div>
                        <p className="text-xs text-muted-foreground">Largest cost center</p>
                    </CardContent>
                </Card>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
                {/* Cost Trend Chart */}
                <Card className="col-span-2 glass-card border-slate-700/50">
                    <CardHeader>
                        <CardTitle>30-Day Cost Trend</CardTitle>
                        <CardDescription>Daily spend analysis</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="h-[300px] w-full mt-4">
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={data?.history || []}>
                                    <defs>
                                        <linearGradient id="colorCost" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                                            <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
                                    <XAxis dataKey="date" stroke="#94a3b8" fontSize={12} tickLine={false} axisLine={false} tickFormatter={(val) => val.slice(5)} />
                                    <YAxis stroke="#94a3b8" fontSize={12} tickLine={false} axisLine={false} tickFormatter={(value) => `$${value}`} />
                                    <Tooltip
                                        contentStyle={{ backgroundColor: '#1e293b', borderColor: '#334155', borderRadius: '8px' }}
                                        itemStyle={{ color: '#10b981' }}
                                        formatter={(value: number) => [`$${value}`, 'Cost']}
                                    />
                                    <Area type="monotone" dataKey="cost" stroke="#10b981" strokeWidth={2} fillOpacity={1} fill="url(#colorCost)" />
                                </AreaChart>
                            </ResponsiveContainer>
                        </div>
                    </CardContent>
                </Card>

                {/* Recommendations */}
                <Card className="col-span-1 glass-card border-slate-700/50">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <CheckCircle className="h-5 w-5 text-emerald-400" />
                            Optimization Plan
                        </CardTitle>
                        <CardDescription>Actionable recommendations</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-4 max-h-[350px] overflow-y-auto pr-2 custom-scrollbar">
                            {recommendations.length === 0 ? (
                                <div className="text-center py-8 text-muted-foreground">No recommendations available.</div>
                            ) : (
                                recommendations.map((rec) => (
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
                                ))
                            )}
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
