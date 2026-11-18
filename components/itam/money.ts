// The one money formatter for ITAM cost figures (Phases 78-80): integer cents in, "$1,234.56" out. The tenant's
// currency is implicit (multi-currency is deferred, COST-F2), so the symbol is the one the console always showed.
// A missing figure is "Not tracked", never $0.

export type LicenseCostPeriod = 'one_time' | 'monthly' | 'annual';
export const PERIOD_LABEL: Record<LicenseCostPeriod, string> = { one_time: 'one-time', monthly: 'per month', annual: 'per year' };
export const NOT_TRACKED = 'Not tracked';

export const formatCents = (cents: number, opts: { whole?: boolean } = {}): string =>
    `$${(cents / 100).toLocaleString(undefined, opts.whole
        ? { maximumFractionDigits: 0 }
        : { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/** A figure that may be missing: the amount, or "Not tracked". */
export const formatMaybeCents = (cents: number | null | undefined, opts: { whole?: boolean } = {}): string =>
    (typeof cents === 'number' ? formatCents(cents, opts) : NOT_TRACKED);

/** "1,299.99" or "$1299" as whole cents, computed from the text (no float rounding); null when it is not an
 *  amount with at most two decimals. */
export const parseAmountToCents = (text: string): number | null => {
    const clean = text.trim().replace(/^\$/, '').replace(/,/g, '');
    const m = /^(\d{1,11})(?:\.(\d{1,2}))?$/.exec(clean);
    if (!m) return null;
    return Number(m[1]) * 100 + Number((m[2] ?? '').padEnd(2, '0'));
};

/** Whole cents as the text an amount field starts with: 129999 -> "1299.99". */
export const centsToAmount = (cents: number): string => `${Math.floor(cents / 100)}.${String(cents % 100).padStart(2, '0')}`;
