/**
 * Ranking for the command palette: instant, local and forgiving, so "go to assets" never waits on an
 * AI round trip. Higher is better; 0 means no match.
 *   exact label 100 · label prefix 80 · word prefix 60 · substring 40 · keyword hit 25 ·
 *   group hit 15 · in-order letters ("ptch" → "Patching") 10
 * When any name matches, group-only and letter-only hits are dropped, so "asset" lists the asset
 * pages rather than every page filed under "Infrastructure & Assets".
 */
export interface Searchable {
    label: string;
    keywords?: string[];
    group?: string;
}

const norm = (s: string) => s.toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '').trim();

const isSubsequence = (needle: string, hay: string) => {
    let i = 0;
    for (const ch of hay) if (ch === needle[i]) i++;
    return i === needle.length;
};

function scoreOne(term: string, item: Searchable): number {
    const label = norm(item.label);
    if (label === term) return 100;
    if (label.startsWith(term)) return 80;
    if (label.split(/[\s/&()·-]+/).some(w => w.startsWith(term))) return 60;
    if (label.includes(term)) return 40;
    const wordHit = (text: string) => norm(text).split(/[\s/&()·-]+/).some(w => w.startsWith(term));
    if ((item.keywords ?? []).some(wordHit)) return 25;
    if (item.group && wordHit(item.group)) return 15;
    if (term.length >= 3 && isSubsequence(term, label.replace(/\s+/g, ''))) return 10;
    return 0;
}

/** Every word of the query must match; the score is the weakest word's (so all words matter). */
export function scoreItem(query: string, item: Searchable): number {
    const words = norm(query).replace(/^(go to|goto|open|show)\s+/, '').split(/\s+/).filter(Boolean);
    if (words.length === 0) return 0;
    let min = Infinity;
    for (const w of words) {
        const s = scoreOne(w, item);
        if (s === 0) return 0;
        min = Math.min(min, s);
    }
    return min;
}

export function rankItems<T extends Searchable>(query: string, items: T[], limit = 8): T[] {
    const scored = items.map((item, index) => ({ item, index, score: scoreItem(query, item) }));
    const floor = scored.some(r => r.score >= 40) ? 25 : 1;
    return scored
        .filter(r => r.score >= floor)
        .sort((a, b) => b.score - a.score || a.item.label.length - b.item.label.length || a.index - b.index)
        .slice(0, limit)
        .map(r => r.item);
}
