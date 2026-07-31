/**
 * Shared geo-formatting helpers used by AgentList.tsx (agent card view) and
 * AgentLocationHistory.tsx (GAUD-02 location-history timeline panel).
 *
 * Extracted verbatim from components/AgentList.tsx — no behavior change.
 */

// ISO 3166-1 alpha-2 code -> flag emoji (regional indicator symbols).
export const flagEmoji = (code?: string): string => {
    if (!code || code.length !== 2) return '';
    const cc = code.toUpperCase();
    if (!/^[A-Z]{2}$/.test(cc)) return '';
    return String.fromCodePoint(...[...cc].map(c => 0x1f1e6 + c.charCodeAt(0) - 65));
};

// "City, Region, Country" from a geo object, skipping empty parts.
export const formatGeo = (geo?: { city?: string; region?: string; country?: string }): string =>
    [geo?.city, geo?.region, geo?.country].filter(Boolean).join(', ');
