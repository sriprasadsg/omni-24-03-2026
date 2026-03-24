import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Shield, Fingerprint, Search, Award, AlertTriangle, CheckCircle, Database } from 'lucide-react';
import { apiService } from '../services/apiService';
import { Progress } from "@/components/ui/progress";

interface CatalogEntry {
    name: string;
    classification: string;
    owner: string;
    retention_days: number;
}

interface QualityReport {
    overall_quality_score: number;
    total_records_scanned: number;
    quarantined_count: number;
    common_issues: string[];
    status: string;
}

export function DataGovernanceDashboard() {
    const [catalog, setCatalog] = useState<CatalogEntry[]>([]);
    const [report, setReport] = useState<QualityReport | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [scanResult, setScanResult] = useState<any>(null);

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        setIsLoading(true);
        try {
            const [catalogRes, reportRes] = await Promise.all([
                apiService.get('/api/governance/catalog'),
                apiService.get('/api/quality/report')
            ]);
            setCatalog(catalogRes);
            setReport(reportRes);
        } catch (error) {
            console.error("Failed to fetch governance data:", error);
        } finally {
            setIsLoading(false);
        }
    };

    const runSampleScan = async () => {
        try {
            // Simulate scanning a sensitive record
            const sampleData = {
                name: "John Doe",
                email: "john.doe@example.com",
                ssn: "123-45-6789", // PII
                notes: "Customer record"
            };
            const res = await apiService.post('/api/governance/scan', sampleData);
            setScanResult(res);
        } catch (error) {
            console.error("Scan failed:", error);
        }
    };

    const getClassificationColor = (classification: string) => {
        switch (classification) {
            case 'CONFIDENTIAL': return 'bg-orange-500/20 text-orange-400 border-orange-500/30';
            case 'RESTRICTED': return 'bg-red-500/20 text-red-400 border-red-500/30';
            case 'INTERNAL': return 'bg-blue-500/20 text-blue-400 border-blue-500/30';
            case 'PUBLIC': return 'bg-green-500/20 text-green-400 border-green-500/30';
            default: return 'bg-gray-500/20 text-gray-400';
        }
    };

    return (
        <div className="space-y-6 pt-6 pb-10 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-emerald-400 to-cyan-400 bg-clip-text text-transparent">
                        Data Governance & Quality
                    </h2>
                    <p className="text-muted-foreground mt-1">
                        Compliance, Privacy, and Data Reliability Center
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
                        <CardTitle className="text-sm font-medium">Quality Score</CardTitle>
                        <Award className="h-4 w-4 text-yellow-400" />
                    </CardHeader>
                    <CardContent>
                        <div className="flex items-center gap-2">
                            <div className="text-2xl font-bold">{report?.overall_quality_score || 0}%</div>
                            {report?.overall_quality_score && report.overall_quality_score > 80 ? (
                                <Badge variant="outline" className="bg-green-500/10 text-green-400 border-green-500/20">Excellent</Badge>
                            ) : (
                                <Badge variant="outline" className="bg-yellow-500/10 text-yellow-400 border-yellow-500/20">Needs Work</Badge>
                            )}
                        </div>
                        <Progress value={report?.overall_quality_score || 0} className="mt-3 h-2" />
                    </CardContent>
                </Card>

                <Card className="glass-card border-slate-700/50">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Records Scanned</CardTitle>
                        <Search className="h-4 w-4 text-blue-400" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{report?.total_records_scanned?.toLocaleString() || 0}</div>
                        <p className="text-xs text-muted-foreground">Total objects validated</p>
                    </CardContent>
                </Card>

                <Card className="glass-card border-slate-700/50">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Quarantined</CardTitle>
                        <AlertTriangle className="h-4 w-4 text-red-400" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{report?.quarantined_count || 0}</div>
                        <p className="text-xs text-muted-foreground">Invalid records blocked</p>
                    </CardContent>
                </Card>

                <Card className="glass-card border-slate-700/50">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">GDPR Status</CardTitle>
                        <Shield className="h-4 w-4 text-green-400" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-green-400">Compliant</div>
                        <p className="text-xs text-muted-foreground">All scanners active</p>
                    </CardContent>
                </Card>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
                {/* Data Catalog */}
                <Card className="col-span-2 glass-card border-slate-700/50">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Database className="h-5 w-5 text-indigo-400" />
                            Data Catalog & Classification
                        </CardTitle>
                        <CardDescription>Inventory of data assets with sensitivity tags</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <Table>
                            <TableHeader>
                                <TableRow className="border-slate-700 hover:bg-transparent">
                                    <TableHead className="text-slate-400">Dataset Name</TableHead>
                                    <TableHead className="text-slate-400">Owner</TableHead>
                                    <TableHead className="text-slate-400">Classification</TableHead>
                                    <TableHead className="text-right text-slate-400">Retention (Days)</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {catalog.length === 0 ? (
                                    <TableRow>
                                        <TableCell colSpan={4} className="text-center py-8 text-muted-foreground">No catalog entries found.</TableCell>
                                    </TableRow>
                                ) : (
                                    catalog.map((entry, i) => (
                                        <TableRow key={i} className="border-slate-700/50 hover:bg-slate-800/30">
                                            <TableCell className="font-medium text-slate-200">{entry.name}</TableCell>
                                            <TableCell>{entry.owner}</TableCell>
                                            <TableCell>
                                                <Badge variant="outline" className={getClassificationColor(entry.classification)}>
                                                    {entry.classification}
                                                </Badge>
                                            </TableCell>
                                            <TableCell className="text-right text-mono">{entry.retention_days}</TableCell>
                                        </TableRow>
                                    ))
                                )}
                            </TableBody>
                        </Table>
                    </CardContent>
                </Card>

                {/* Tools & Scanner */}
                <div className="space-y-4">
                    <Card className="glass-card border-slate-700/50">
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <Fingerprint className="h-5 w-5 text-purple-400" />
                                PII Scanner
                            </CardTitle>
                            <CardDescription>Test interactive data scanning</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="space-y-4">
                                <p className="text-sm text-muted-foreground">Click to scan a sample record containing SSN and Email.</p>
                                <Button onClick={runSampleScan} className="w-full bg-indigo-600 hover:bg-indigo-700">Run PII Scan</Button>

                                {scanResult && (
                                    <div className="rounded-md bg-slate-900/50 p-3 border border-slate-700 text-sm space-y-2 mt-4">
                                        <div className="flex justify-between">
                                            <span className="text-muted-foreground">Classification:</span>
                                            <Badge variant="outline" className={getClassificationColor(scanResult.classification)}>
                                                {scanResult.classification}
                                            </Badge>
                                        </div>
                                        <div>
                                            <span className="text-muted-foreground block mb-1">PII Detected:</span>
                                            <div className="flex gap-1 flex-wrap">
                                                {scanResult.pii_detected.map((p: string) => (
                                                    <Badge key={p} variant="secondary" className="bg-red-500/10 text-red-400 border-red-500/20 text-xs">{p}</Badge>
                                                ))}
                                            </div>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </CardContent>
                    </Card>

                    <Card className="glass-card border-slate-700/50">
                        <CardHeader>
                            <CardTitle>Common Issues</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <ul className="space-y-2">
                                {report?.common_issues.map((issue, i) => (
                                    <li key={i} className="flex items-center gap-2 text-sm text-amber-200/80">
                                        <AlertTriangle className="h-3 w-3" />
                                        {issue}
                                    </li>
                                ))}
                            </ul>
                        </CardContent>
                    </Card>
                </div>
            </div>
        </div>
    );
}
