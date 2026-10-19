/**
 * Client-side CSV export. Cells are quoted per RFC 4180, and a cell that a spreadsheet would run as a
 * formula (leading = + - @ tab or CR) gets a leading apostrophe: hostnames and package names come from
 * agents, so they are untrusted text.
 */
export function csvCell(value: unknown): string {
    let s = value === null || value === undefined ? '' : String(value);
    if (/^[=+\-@\t\r]/.test(s)) s = `'${s}`;
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function toCsv(headers: string[], rows: unknown[][]): string {
    return [headers, ...rows].map(r => r.map(csvCell).join(',')).join('\r\n');
}

/** Hand the browser a CSV file to save (a BOM keeps Excel from mangling UTF-8). */
export function downloadCsv(filename: string, csv: string): void {
    const blob = new Blob(['﻿', csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
}
