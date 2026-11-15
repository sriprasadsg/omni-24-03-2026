import React, { useEffect, useRef, useState } from 'react';

export const SCROLL_HINT = 'Scroll sideways to see every column.';

interface ScrollRegionProps {
    /** The table's caption; the region is named "Scrollable: <label>" so it never repeats the caption word for word. */
    label: string;
    /** A tab stop while it scrolls, for a table with no focusable content of its own (axe scrollable-region-focusable). */
    focusable?: boolean;
    children: React.ReactNode;
}

/**
 * The sideways scroll wrapper of a wide Autonomous Ops table (G-86-5). While the table is wider than its card it is a
 * named region, shows a fade on the right edge while columns are hidden there and a hint under it (review WR-07: an
 * overlay scrollbar hides until scrolled, so the Action column could go unseen), and with ``focusable`` it is a tab
 * stop. While the table fits it is a plain wrapper, with no extra landmark and no extra tab stop (review IN-06).
 */
export const ScrollRegion: React.FC<ScrollRegionProps> = ({ label, focusable = false, children }) => {
    const ref = useRef<HTMLDivElement>(null);
    const [edge, setEdge] = useState({ overflow: false, more: false });
    useEffect(() => {
        const el = ref.current;
        if (!el) return undefined;
        const measure = () => {
            const overflow = el.scrollWidth > el.clientWidth + 1;
            const more = overflow && el.scrollLeft + el.clientWidth < el.scrollWidth - 1;
            setEdge(prev => (prev.overflow === overflow && prev.more === more ? prev : { overflow, more }));
        };
        measure();
        el.addEventListener('scroll', measure, { passive: true });
        window.addEventListener('resize', measure);
        const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(measure) : null;
        observer?.observe(el);
        if (el.firstElementChild) observer?.observe(el.firstElementChild);
        return () => {
            el.removeEventListener('scroll', measure);
            window.removeEventListener('resize', measure);
            observer?.disconnect();
        };
    }, []);
    const region = edge.overflow
        ? { role: 'region', 'aria-label': `Scrollable: ${label}`, ...(focusable ? { tabIndex: 0 } : {}) }
        : {};
    return (
        <div className="min-w-0">
            <div className="relative min-w-0">
                <div ref={ref} className="min-w-0 overflow-x-auto" {...region}>{children}</div>
                {edge.more && (
                    <div aria-hidden="true" data-scroll-fade=""
                        className="pointer-events-none absolute inset-y-0 right-0 w-8 bg-gradient-to-l from-black/10 to-transparent dark:from-white/10" />
                )}
            </div>
            {edge.overflow && <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{SCROLL_HINT}</p>}
        </div>
    );
};

export default ScrollRegion;
