import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Zap, Activity, HelpCircle, BarChart2 } from 'lucide-react';
import { fetchGlobalImportance, explainPrediction } from '../services/apiService';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, ReferenceLine } from 'recharts';

export function XAIDashboard() {
    const [globalImportance, setGlobalImportance] = useState<any[]>([]);
    const [inputs, setInputs] = useState({
        failed_logins_count: 0,
        ip_reputation_score: 90,
        access_time_hour: 14
    });
    const [explanation, setExplanation] = useState<any>(null);
    const [isLoading, setIsLoading] = useState(false);

    useEffect(() => {
        loadGlobalImportance();
    }, []);

    const loadGlobalImportance = async () => {
        try {
            const res = await fetchGlobalImportance('model-risk-v1');
            setGlobalImportance(res);
        } catch (error) {
            console.error("Failed to fetch global importance:", error);
        }
    };

    const runExplanation = async () => {
        setIsLoading(true);
        try {
            const res = await explainPrediction('model-risk-v1', inputs);
            setExplanation(res);
        } catch (error) {
            console.error("Failed to explain prediction:", error);
        } finally {
            setIsLoading(false);
        }
    };

    const handleInputChange = (key: string, value: number) => {
        setInputs(prev => ({ ...prev, [key]: value }));
    };

    return (
        <div className="space-y-6 pt-6 pb-10 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-pink-400 to-rose-400 bg-clip-text text-transparent">
                        AI Explainability (XAI)
                    </h2>
                    <p className="text-muted-foreground mt-1">
                        Understanding Model Decisions with SHAP
                    </p>
                </div>
            </div>

            <div className="grid gap-6 md:grid-cols-2">
                {/* Global Importance */}
                <Card className="glass-card border-slate-700/50">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <BarChart2 className="h-5 w-5 text-pink-400" />
                            Global Feature Importance
                        </CardTitle>
                        <CardDescription>Top drivers of model predictions overall</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="h-[300px] w-full">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart layout="vertical" data={globalImportance} margin={{ left: 20 }}>
                                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#334155" />
                                    <XAxis type="number" stroke="#94a3b8" fontSize={12} />
                                    <YAxis dataKey="feature" type="category" stroke="#94a3b8" fontSize={12} width={120} />
                                    <Tooltip cursor={{ fill: '#334155', opacity: 0.2 }} contentStyle={{ backgroundColor: '#1e293b', borderColor: '#334155' }} />
                                    <Bar dataKey="importance" fill="#f472b6" radius={[0, 4, 4, 0]} />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </CardContent>
                </Card>

                {/* Prediction Simulator */}
                <Card className="glass-card border-slate-700/50">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Activity className="h-5 w-5 text-blue-400" />
                            Prediction Simulator
                        </CardTitle>
                        <CardDescription>Adjust inputs to see how risk changes</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-6">
                        <div className="space-y-4">
                            <div className="space-y-2">
                                <div className="flex justify-between">
                                    <Label>Failed Logins: {inputs.failed_logins_count}</Label>
                                </div>
                                <Slider
                                    value={inputs.failed_logins_count}
                                    max={10} step={1}
                                    onChange={(e) => handleInputChange('failed_logins_count', parseInt(e.target.value))}
                                    className="py-2"
                                />
                            </div>

                            <div className="space-y-2">
                                <div className="flex justify-between">
                                    <Label>IP Reputation: {inputs.ip_reputation_score}</Label>
                                </div>
                                <Slider
                                    value={inputs.ip_reputation_score}
                                    max={100} step={5}
                                    onChange={(e) => handleInputChange('ip_reputation_score', parseInt(e.target.value))}
                                    className="py-2"
                                />
                            </div>

                            <div className="space-y-2">
                                <div className="flex justify-between">
                                    <Label>Access Time (Hour): {inputs.access_time_hour}:00</Label>
                                </div>
                                <Slider
                                    value={inputs.access_time_hour}
                                    max={23} step={1}
                                    onChange={(e) => handleInputChange('access_time_hour', parseInt(e.target.value))}
                                    className="py-2"
                                />
                            </div>
                        </div>

                        <Button onClick={runExplanation} disabled={isLoading} className="w-full bg-pink-600 hover:bg-pink-700">
                            {isLoading ? 'Analyzing...' : 'Explain Prediction'}
                        </Button>
                    </CardContent>
                </Card>

                {/* Local Explanation (SHAP) */}
                {explanation && (
                    <Card className="col-span-2 glass-card border-slate-700/50 bg-gradient-to-r from-slate-900/50 to-pink-900/10">
                        <CardHeader>
                            <CardTitle className="flex justify-between items-center">
                                <div className="flex items-center gap-2">
                                    <Zap className="h-5 w-5 text-yellow-400" />
                                    Prediction Explanation
                                </div>
                                <Badge variant="outline" className={explanation.risk_level === 'HIGH' ? 'bg-red-500/20 text-red-400 border-red-500/50' : 'bg-green-500/20 text-green-400 border-green-500/50'}>
                                    {explanation.risk_level} RISK ({(explanation.prediction * 100).toFixed(1)}%)
                                </Badge>
                            </CardTitle>
                            <CardDescription>
                                Base Value: {(explanation.base_value * 100).toFixed(1)}% | Impact of current features shown below
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="h-[250px] w-full">
                                <ResponsiveContainer width="100%" height="100%">
                                    <BarChart data={explanation.features} layout="vertical" margin={{ left: 40, right: 40 }}>
                                        <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#334155" />
                                        <XAxis type="number" hide />
                                        <YAxis dataKey="feature" type="category" stroke="#94a3b8" fontSize={12} width={150} />
                                        <Tooltip
                                            cursor={{ fill: '#334155', opacity: 0.2 }}
                                            content={({ active, payload }) => {
                                                if (active && payload && payload.length) {
                                                    const data = payload[0].payload;
                                                    return (
                                                        <div className="bg-slate-800 border border-slate-700 p-2 rounded text-xs">
                                                            <div className="font-bold">{data.feature}</div>
                                                            <div>Value: {data.value}</div>
                                                            <div className={data.shap > 0 ? "text-red-400" : "text-green-400"}>
                                                                Impact: {data.shap > 0 ? "+" : ""}{(data.shap * 100).toFixed(1)}%
                                                            </div>
                                                        </div>
                                                    );
                                                }
                                                return null;
                                            }}
                                        />
                                        <ReferenceLine x={0} stroke="#94a3b8" />
                                        <Bar dataKey="shap" name="Impact">
                                            {explanation.features.map((entry: any, index: number) => (
                                                <Cell key={`cell-${index}`} fill={entry.shap >= 0 ? '#ef4444' : '#22c55e'} />
                                            ))}
                                        </Bar>
                                    </BarChart>
                                </ResponsiveContainer>
                            </div>
                        </CardContent>
                    </Card>
                )}
            </div>
        </div>
    );
}
