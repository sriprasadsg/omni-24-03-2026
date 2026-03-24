import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { GitBranch, Play, RefreshCw, CheckCircle, Clock, AlertTriangle, Box, ArrowUpCircle } from 'lucide-react';
import { apiService } from '../services/apiService';
import { Progress } from "@/components/ui/progress";

interface ModelEntry {
    id: string;
    name: string;
    version: string;
    stage: string;
    accuracy: number;
    created_at: string;
}

interface TrainingJob {
    job_id: string;
    model_name: string;
    status: string;
    progress: number;
    start_time: string;
    end_time?: string;
    metrics?: {
        accuracy: number;
        f1_score: number;
    };
}

export function MLOpsDashboard() {
    const [models, setModels] = useState<ModelEntry[]>([]);
    const [jobs, setJobs] = useState<TrainingJob[]>([]);
    const [activeJobId, setActiveJobId] = useState<string | null>(null);

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 3000); // Polling for active jobs
        return () => clearInterval(interval);
    }, []);

    const fetchData = async () => {
        try {
            const [modelsRes, jobsRes] = await Promise.all([
                apiService.get('/api/mlops/models'),
                apiService.get('/api/mlops/history')
            ]);
            setModels(modelsRes);
            setJobs(jobsRes);

            // Check if active job completed
            if (activeJobId) {
                const job = jobsRes.find((j: any) => j.job_id === activeJobId);
                if (job && (job.status === 'Completed' || job.status === 'Failed')) {
                    setActiveJobId(null);
                }
            }
        } catch (error) {
            console.error("Failed to fetch MLOps data:", error);
        }
    };

    const triggerTraining = async (modelName: string) => {
        try {
            const res = await apiService.post('/api/mlops/train', { model_name: modelName });
            setActiveJobId(res.job_id);
            fetchData(); // Immediate update
        } catch (error) {
            console.error("Failed to trigger training:", error);
        }
    };

    const promoteModel = async (modelId: string) => {
        try {
            await apiService.post('/api/mlops/promote', { model_id: modelId });
            fetchData();
        } catch (error) {
            console.error("Failed to promote model:", error);
        }
    };

    const getStageColor = (stage: string) => {
        switch (stage) {
            case 'Production': return 'bg-green-500/10 text-green-400 border-green-500/20';
            case 'Staging': return 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20';
            case 'Archived': return 'bg-gray-500/10 text-gray-400 border-gray-500/20';
            default: return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
        }
    };

    return (
        <div className="space-y-6 pt-6 pb-10 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-violet-400 to-fuchsia-400 bg-clip-text text-transparent">
                        MLOps Control Center
                    </h2>
                    <p className="text-muted-foreground mt-1">
                        Automated Training Pipelines & Model Registry
                    </p>
                </div>
                <Button onClick={fetchData} variant="outline" className="border-slate-700 hover:bg-slate-800">
                    <RefreshCw className="mr-2 h-4 w-4" /> Refresh
                </Button>
            </div>

            <div className="grid gap-6 md:grid-cols-2">
                {/* Model Registry */}
                <Card className="glass-card border-slate-700/50 col-span-2">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Box className="h-5 w-5 text-indigo-400" />
                            Model Registry
                        </CardTitle>
                        <CardDescription>Versioned models and deployment stages</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <Table>
                            <TableHeader>
                                <TableRow className="border-slate-700 hover:bg-transparent">
                                    <TableHead className="text-slate-400">Model Name</TableHead>
                                    <TableHead className="text-slate-400">Version</TableHead>
                                    <TableHead className="text-slate-400">Stage</TableHead>
                                    <TableHead className="text-slate-400">Accuracy</TableHead>
                                    <TableHead className="text-slate-400">Created</TableHead>
                                    <TableHead className="text-right text-slate-400">Actions</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {models.map((model) => (
                                    <TableRow key={model.id} className="border-slate-700/50 hover:bg-slate-800/30">
                                        <TableCell className="font-medium text-slate-200">{model.name}</TableCell>
                                        <TableCell className="font-mono text-xs">{model.version}</TableCell>
                                        <TableCell>
                                            <Badge variant="outline" className={getStageColor(model.stage)}>
                                                {model.stage}
                                            </Badge>
                                        </TableCell>
                                        <TableCell className="text-green-400 font-bold">{(model.accuracy * 100).toFixed(1)}%</TableCell>
                                        <TableCell className="text-muted-foreground text-xs">{new Date(model.created_at).toLocaleDateString()}</TableCell>
                                        <TableCell className="text-right flex justify-end gap-2">
                                            {model.stage === 'Production' ? (
                                                <Button size="sm" variant="ghost" disabled className="text-green-500 opacity-50"><CheckCircle className="h-4 w-4 mr-1" /> Live</Button>
                                            ) : model.stage === 'Staging' ? (
                                                <Button size="sm" variant="outline" onClick={() => promoteModel(model.id)} className="border-green-500/30 text-green-400 hover:bg-green-500/10">
                                                    <ArrowUpCircle className="h-4 w-4 mr-2" /> Promote
                                                </Button>
                                            ) : (
                                                <span className="text-muted-foreground text-xs p-2">Archived</span>
                                            )}

                                            {/* Training Trigger for latest version usually, but here checking by name */}
                                            <Button size="sm" variant="secondary" onClick={() => triggerTraining(model.name)} className="bg-slate-800 hover:bg-slate-700">
                                                <Play className="h-3 w-3 mr-1" /> Retrain
                                            </Button>
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </CardContent>
                </Card>

                {/* Pipeline Visualizer (For Active Jobs) */}
                <Card className="glass-card border-slate-700/50 col-span-2 md:col-span-1">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <GitBranch className="h-5 w-5 text-blue-400" />
                            Active Pipelines
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-6">
                            {jobs.filter(j => j.status !== 'Completed' && j.status !== 'Failed').length === 0 ? (
                                <div className="text-center py-10 text-muted-foreground border-2 border-dashed border-slate-700/50 rounded-lg">
                                    No active training pipelines.
                                </div>
                            ) : (
                                jobs.filter(j => j.status !== 'Completed' && j.status !== 'Failed').map(job => (
                                    <div key={job.job_id} className="space-y-2 p-4 rounded-lg bg-slate-900/40 border border-slate-700/50">
                                        <div className="flex justify-between text-sm">
                                            <span className="font-bold text-slate-200">{job.model_name}</span>
                                            <span className="text-blue-400 animate-pulse">{job.status}</span>
                                        </div>
                                        <Progress value={job.progress} className="h-2" />
                                        <div className="flex justify-between text-xs text-muted-foreground">
                                            <span>Data Prep</span>
                                            <span>Training</span>
                                            <span>Eval</span>
                                            <span>Register</span>
                                        </div>
                                    </div>
                                ))
                            )}
                        </div>
                    </CardContent>
                </Card>

                {/* Training History */}
                <Card className="glass-card border-slate-700/50 col-span-2 md:col-span-1">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Clock className="h-5 w-5 text-gray-400" />
                            Job History
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-3 max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
                            {jobs.map(job => (
                                <div key={job.job_id} className="flex justify-between items-center p-3 rounded bg-slate-800/20 border border-slate-700/30">
                                    <div>
                                        <div className="font-medium text-sm text-slate-300">{job.model_name}</div>
                                        <div className="text-xs text-muted-foreground">{new Date(job.start_time).toLocaleString()}</div>
                                    </div>
                                    <div className="text-right">
                                        <Badge variant="outline" className={job.status === 'Completed' ? 'bg-green-500/10 text-green-400 border-none' : job.status === 'Failed' ? 'bg-red-500/10 text-red-400 border-none' : 'bg-blue-500/10 text-blue-400 border-none'}>
                                            {job.status}
                                        </Badge>
                                        {job.metrics && (
                                            <div className="text-xs text-green-400 mt-1">Acc: {(job.metrics.accuracy * 100).toFixed(1)}%</div>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
