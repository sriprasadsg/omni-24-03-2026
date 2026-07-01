import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Shield, Fingerprint, Search, Award, AlertTriangle, CheckCircle, Database } from 'lucide-react';
import { authFetch } from '../services/apiService';
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

interface LineageNode {
    id: string;
    label: string;
    type: 'source' | 'process' | 'destination';
    classification: string;
    owner?: string;
}

interface LineageEdge {
    source: string;
    target: string;
    label?: string;
}

export function DataGovernanceDashboard() {
    const [catalog, setCatalog] = useState<CatalogEntry[]>([]);
    const [report, setReport] = useState<QualityReport | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [scanResult, setScanResult] = useState<any>(null);
    const [lineageNodes, setLineageNodes] = useState<LineageNode[]>([]);
    const [lineageEdges, setLineageEdges] = useState<LineageEdge[]>([]);
    const [activeTab, setActiveTab] = useState<'overview' | 'lineage'>('overview');

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        setIsLoading(true);
        try {
            const [catalogRes, reportRes, lineageRes] = await Promise.all([
                authFetch('/api/governance/catalog').then(r => r.ok ? r.json() : []),
                authFetch('/api/quality/report').then(r => r.ok ? r.json() : null),
                authFetch('/api/governance/lineage').then(r => r.ok ? r.json() : { nodes: [], edges: [] }),
            ]);
            setCatalog(Array.isArray(catalogRes) ? catalogRes : []);
            setReport(reportRes);
            setLineageNodes(lineageRes.nodes || []);
            setLineageEdges(lineageRes.edges || []);
        } catch (error) {
            console.error("Failed to fetch governance data:", error);
        } finally {
            setIsLoading(false);
        }
    };

    const runSampleScan = async () => {
        try {
            const sampleData = {
                name: "John Doe", email: "john.doe@example.com",
                ssn: "123-45-6789", notes: "Customer record"
            };
            const res = await authFetch('/api/governance/scan', {
                method: 'POST', body: JSON.stringify(sampleData),
            });
            setScanResult(await res.json());
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

    // ── Lineage graph layout helpers ─────────────────────────────────────────
    const NODE_W = 140; const NODE_H = 48; const COL_GAP = 180; const ROW_GAP = 72;
    const COLS: LineageNode['type'][] = ['source', 'process', 'destination'];
    const nodesByCol = COLS.map(col => lineageNodes.filter(n => n.type === col));
    const totalH = Math.max(...nodesByCol.map(c => c.length)) * ROW_GAP + 60;
    const totalW = COLS.length * (NODE_W + COL_GAP) + 60;

    const nodePos = (node: LineageNode) => {
        const col = COLS.indexOf(node.type as LineageNode['type']);
        const rowNodes = nodesByCol[col] || [];
        const row = rowNodes.findIndex(n => n.id === node.id);
        const colH = rowNodes.length * ROW_GAP;
        const yOffset = (totalH - colH) / 2;
        return {
            x: 40 + col * (NODE_W + COL_GAP),
            y: yOffset + row * ROW_GAP + 8,
        };
    };

    const classColor = (c: string) => ({
        CONFIDENTIAL: '#f97316', RESTRICTED: '#ef4444', INTERNAL: '#3b82f6', PUBLIC: '#22c55e'
    }[c] || '#6b7280');

    const colColor = (t: string) => ({ source: '#8b5cf6', process: '#0ea5e9', destination: '#10b981' }[t] || '#6b7280');

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
                <div className="flex items-center gap-3">
                    <div className="flex rounded-lg overflow-hidden border border-slate-700">
                        {(['overview', 'lineage'] as const).map(tab => (
                            <button key={tab} onClick={() => setActiveTab(tab)}
                                className={`px-4 py-1.5 text-sm font-medium capitalize ${activeTab === tab ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'}`}>
                                {tab}
                            </button>
                        ))}
                    </div>
                    <Button onClick={fetchData} variant="outline" className="border-slate-700 hover:bg-slate-800">
                        Refresh Data
                    </Button>
                </div>
            </div>

            {/* Lineage Graph tab */}
            {activeTab === 'lineage' && (
                <Card className="glass-card border-slate-700/50">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2"><Database className="w-5 h-5 text-cyan-400" /> Data Lineage Graph</CardTitle>
                        <CardDescription>Visual flow of data from sources through processing to destinations</CardDescription>
                    </CardHeader>
                    <CardContent>
                        {lineageNodes.length === 0 ? (
                            <div className="text-center py-12 text-slate-500">No lineage data available yet.</div>
                        ) : (
                            <div className="overflow-x-auto">
                                <svg width={totalW} height={totalH} className="font-sans">
                                    {/* Column headers */}
                                    {COLS.map((col, i) => (
                                        <text key={col} x={40 + i * (NODE_W + COL_GAP) + NODE_W / 2} y={18}
                                            textAnchor="middle" fontSize={11} fill={colColor(col)}
                                            fontWeight="bold" style={{ textTransform: 'uppercase', letterSpacing: 1 }}>
                                            {col.toUpperCase()}
                                        </text>
                                    ))}
                                    {/* Edges */}
                                    {lineageEdges.map((edge, i) => {
                                        const srcNode = lineageNodes.find(n => n.id === edge.source);
                                        const dstNode = lineageNodes.find(n => n.id === edge.target);
                                        if (!srcNode || !dstNode) return null;
                                        const src = nodePos(srcNode);
                                        const dst = nodePos(dstNode);
                                        const x1 = src.x + NODE_W; const y1 = src.y + NODE_H / 2;
                                        const x2 = dst.x; const y2 = dst.y + NODE_H / 2;
                                        const cx1 = x1 + (x2 - x1) * 0.5; const cx2 = x2 - (x2 - x1) * 0.5;
                                        return (
                                            <g key={i}>
                                                <path d={`M${x1},${y1} C${cx1},${y1} ${cx2},${y2} ${x2},${y2}`}
                                                    fill="none" stroke="#475569" strokeWidth={1.5} strokeDasharray="4 2" opacity={0.6} />
                                                {edge.label && (
                                                    <text x={(x1 + x2) / 2} y={Math.min(y1, y2) - 4}
                                                        textAnchor="middle" fontSize={9} fill="#94a3b8">{edge.label}</text>
                                                )}
                                            </g>
                                        );
                                    })}
                                    {/* Nodes */}
                                    {lineageNodes.map(node => {
                                        const { x, y } = nodePos(node);
                                        const cc = classColor(node.classification);
                                        const tc = colColor(node.type);
                                        return (
                                            <g key={node.id}>
                                                <rect x={x} y={y} width={NODE_W} height={NODE_H} rx={8}
                                                    fill="#1e293b" stroke={tc} strokeWidth={1.5} />
                                                <rect x={x} y={y} width={4} height={NODE_H} rx={4}
                                                    fill={tc} />
                                                <circle cx={x + NODE_W - 12} cy={y + 12} r={5} fill={cc} opacity={0.9} />
                                                <text x={x + 14} y={y + 19} fontSize={11} fontWeight="bold" fill="#e2e8f0" textAnchor="start">
                                                    {node.label.length > 16 ? node.label.slice(0, 15) + '…' : node.label}
                                                </text>
                                                <text x={x + 14} y={y + 34} fontSize={9} fill="#94a3b8" textAnchor="start">
                                                    {node.owner ? node.owner.slice(0, 18) : node.classification}
                                                </text>
                                            </g>
                                        );
                                    })}
                                </svg>
                                <div className="flex items-center gap-4 mt-4 flex-wrap">
                                    {[['Source', '#8b5cf6'], ['Process', '#0ea5e9'], ['Destination', '#10b981']].map(([l, c]) => (
                                        <div key={l} className="flex items-center gap-1.5 text-xs text-slate-400">
                                            <div className="w-3 h-3 rounded" style={{ background: c as string }} />{l}
                                        </div>
                                    ))}
                                    <div className="ml-4 flex items-center gap-3">
                                        {[['CONFIDENTIAL', '#f97316'], ['RESTRICTED', '#ef4444'], ['INTERNAL', '#3b82f6'], ['PUBLIC', '#22c55e']].map(([l, c]) => (
                                            <div key={l} className="flex items-center gap-1 text-xs text-slate-400">
                                                <div className="w-2.5 h-2.5 rounded-full" style={{ background: c as string }} />{l}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        )}
                    </CardContent>
                </Card>
            )}

            {activeTab === 'overview' && (
            <>{/* Top Stats */}
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
            </>)}
        </div>
    );
}
