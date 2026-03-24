import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Microscope, Play, Plus, GitCommon, Trophy } from 'lucide-react';
import { apiService } from '../services/apiService';
import { ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip, ResponsiveContainer, Label } from 'recharts';

interface Trial {
    trial_id: string;
    params: {
        learning_rate: number;
        batch_size: number;
        optimizer: string;
        layers: number;
    };
    value: number;
    state: string;
}

interface Study {
    id: string;
    name: string;
    trials: Trial[];
    best_trial?: Trial;
}

export function AutoMLDashboard() {
    const [studies, setStudies] = useState<any[]>([]);
    const [selectedStudyId, setSelectedStudyId] = useState<string | null>(null);
    const [studyDetails, setStudyDetails] = useState<Study | null>(null);
    const [isRunning, setIsRunning] = useState(false);

    useEffect(() => {
        fetchStudies();
    }, []);

    useEffect(() => {
        if (selectedStudyId) {
            fetchDetails(selectedStudyId);
            const interval = setInterval(() => fetchDetails(selectedStudyId), 2000);
            return () => clearInterval(interval);
        }
    }, [selectedStudyId]);

    const fetchStudies = async () => {
        try {
            const res = await apiService.get('/api/automl/studies');
            setStudies(res);
            // Auto-select first study if none selected
            if (!selectedStudyId && res.length > 0) {
                setSelectedStudyId(res[0].id);
            }
        } catch (error) {
            console.error("Failed to fetch studies:", error);
        }
    };

    const fetchDetails = async (id: string) => {
        try {
            const res = await apiService.get(`/api/automl/study/${id}`);
            setStudyDetails(res);
        } catch (error) {
            console.error("Failed to fetch study details:", error);
        }
    };

    const createStudy = async () => {
        try {
            const name = prompt("Enter Study Name (e.g., 'Optimize LSTM'):");
            if (name) {
                const res = await apiService.post('/api/automl/study', { name });
                fetchStudies();
                setSelectedStudyId(res.study_id);
            }
        } catch (error) {
            console.error("Failed to create study:", error);
        }
    };

    const runTrials = async () => {
        if (!selectedStudyId) return;
        setIsRunning(true);
        try {
            await apiService.post(`/api/automl/study/${selectedStudyId}/run`, { n_trials: 10 });
            fetchDetails(selectedStudyId);
        } catch (error) {
            console.error("Failed to run trials:", error);
        } finally {
            setIsRunning(false);
        }
    };

    // Prepare chart data: Scatter plot of LR vs Accuracy
    const chartData = studyDetails?.trials.map(t => ({
        x: t.params.learning_rate,
        y: t.value,
        z: t.params.batch_size, // bubble size attempt or tooltip
        optimizer: t.params.optimizer
    })) || [];

    return (
        <div className="space-y-6 pt-6 pb-10 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-orange-400 to-amber-400 bg-clip-text text-transparent">
                        AutoML Studio
                    </h2>
                    <p className="text-muted-foreground mt-1">
                        Automated Hyperparameter Optimization (Simulated Optuna)
                    </p>
                </div>
                <div className="flex gap-2">
                    <Button onClick={createStudy} variant="outline" className="border-slate-700 hover:bg-slate-800">
                        <Plus className="mr-2 h-4 w-4" /> New Study
                    </Button>
                    {selectedStudyId && (
                        <Button onClick={runTrials} disabled={isRunning} className="bg-gradient-to-r from-orange-600 to-amber-600 hover:from-orange-700 hover:to-amber-700">
                            <Play className={`mr-2 h-4 w-4 ${isRunning ? 'animate-spin' : ''}`} />
                            {isRunning ? 'Optimizing...' : 'Run 10 Trials'}
                        </Button>
                    )}
                </div>
            </div>

            <div className="grid gap-6 md:grid-cols-7">
                {/* Studies List */}
                <Card className="col-span-2 glass-card border-slate-700/50">
                    <CardHeader>
                        <CardTitle className="text-sm font-medium">Experiments</CardTitle>
                    </CardHeader>
                    <CardContent className="p-0">
                        <div className="space-y-1">
                            {studies.length === 0 && <div className="p-4 text-sm text-muted-foreground text-center">No studies yet.</div>}
                            {studies.map(study => (
                                <div
                                    key={study.id}
                                    onClick={() => setSelectedStudyId(study.id)}
                                    className={`p-3 cursor-pointer transition-colors border-l-2 ${selectedStudyId === study.id ? 'bg-slate-800/50 border-orange-500' : 'hover:bg-slate-800/30 border-transparent'}`}
                                >
                                    <div className="font-medium text-slate-200">{study.name}</div>
                                    <div className="flex justify-between text-xs text-muted-foreground mt-1">
                                        <span>{study.trials_count} trials</span>
                                        <span className="text-green-400">Best: {(study.best_score * 100).toFixed(1)}%</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>

                {/* Main Content */}
                <div className="col-span-5 space-y-4">
                    {studyDetails ? (
                        <>
                            {/* Best Result Box */}
                            {studyDetails.best_trial && (
                                <Card className="glass-card border-slate-700/50 bg-gradient-to-br from-slate-900/50 to-orange-900/10">
                                    <CardContent className="pt-6 flex items-start gap-4">
                                        <div className="p-3 rounded-full bg-orange-500/20 text-orange-400">
                                            <Trophy className="h-6 w-6" />
                                        </div>
                                        <div>
                                            <div className="text-sm text-muted-foreground uppercase tracking-wider font-semibold">Best Configuration Found</div>
                                            <div className="text-3xl font-bold text-white mt-1">{(studyDetails.best_trial.value * 100).toFixed(2)}% Accuracy</div>
                                            <div className="flex gap-4 mt-2 text-sm text-slate-300">
                                                <Badge variant="outline" className="border-slate-600">LR: {studyDetails.best_trial.params.learning_rate}</Badge>
                                                <Badge variant="outline" className="border-slate-600">Batch: {studyDetails.best_trial.params.batch_size}</Badge>
                                                <Badge variant="outline" className="border-slate-600 capitalize">Opt: {studyDetails.best_trial.params.optimizer}</Badge>
                                                <Badge variant="outline" className="border-slate-600">Layers: {studyDetails.best_trial.params.layers}</Badge>
                                            </div>
                                        </div>
                                    </CardContent>
                                </Card>
                            )}

                            {/* Charts */}
                            <div className="grid md:grid-cols-2 gap-4">
                                <Card className="glass-card border-slate-700/50">
                                    <CardHeader>
                                        <CardTitle className="text-sm">Trial History</CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        <div className="h-[200px] w-full">
                                            <ResponsiveContainer width="100%" height="100%">
                                                <ScatterChart>
                                                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                                                    <XAxis type="number" dataKey="x" name="Learning Rate" stroke="#94a3b8" fontSize={12} label={{ value: 'Learning Rate', position: 'insideBottom', offset: -5 }} />
                                                    <YAxis type="number" dataKey="y" name="Accuracy" stroke="#94a3b8" fontSize={12} domain={[0, 1]} />
                                                    <Tooltip cursor={{ strokeDasharray: '3 3' }} contentStyle={{ backgroundColor: '#1e293b', borderColor: '#334155' }} />
                                                    <Scatter name="Trials" data={chartData} fill="#f97316" />
                                                </ScatterChart>
                                            </ResponsiveContainer>
                                        </div>
                                    </CardContent>
                                </Card>

                                <Card className="glass-card border-slate-700/50">
                                    <CardHeader>
                                        <CardTitle className="text-sm">Leaderboard (Top 5)</CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        <Table>
                                            <TableHeader>
                                                <TableRow className="border-none hover:bg-transparent text-xs">
                                                    <TableHead className="py-1">Rank</TableHead>
                                                    <TableHead className="py-1">Score</TableHead>
                                                    <TableHead className="py-1 text-right">Params</TableHead>
                                                </TableRow>
                                            </TableHeader>
                                            <TableBody>
                                                {[...studyDetails.trials].sort((a, b) => b.value - a.value).slice(0, 5).map((t, i) => (
                                                    <TableRow key={t.trial_id} className="border-slate-700/30 text-xs">
                                                        <TableCell className="py-2 text-muted-foreground">#{i + 1}</TableCell>
                                                        <TableCell className="py-2 font-bold text-orange-400">{(t.value * 100).toFixed(1)}%</TableCell>
                                                        <TableCell className="py-2 text-right text-slate-400">
                                                            LR:{t.params.learning_rate} | B:{t.params.batch_size}
                                                        </TableCell>
                                                    </TableRow>
                                                ))}
                                            </TableBody>
                                        </Table>
                                    </CardContent>
                                </Card>
                            </div>
                        </>
                    ) : (
                        <div className="h-full flex items-center justify-center text-muted-foreground border-2 border-dashed border-slate-700/50 rounded-lg">
                            Select or Create a Study to view details.
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
