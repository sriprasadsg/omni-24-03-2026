import { useCallback, useEffect, useRef } from 'react';
import type cytoscape from 'cytoscape';
import { FLOW_COLORS } from './topologyStyle';

// Motion on the Network Topology map, all of it driven by measured data:
//  - dashes march along each endpoint uplink that moves data (edge[?active]), faster as the measured
//    rate grows, in the direction most bytes go;
//  - a packet pulse runs along a link when a new measurement or flow event arrives.
// Nothing moves under prefers-reduced-motion, and nothing runs while the tab is hidden.

interface Packet { sourceId: string; targetId: string; progress: number; blocked: boolean }

export const prefersReducedMotion = () =>
    typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

export function useTopologyMotion(
    cyRef: React.MutableRefObject<cytoscape.Core | null>,
    canvasRef: React.RefObject<HTMLCanvasElement | null>,
    dark: boolean,
) {
    const packetsRef = useRef<Packet[]>([]);
    const frameRef = useRef<number | undefined>(undefined);

    useEffect(() => {
        if (prefersReducedMotion()) return;
        let tick = 0;
        const id = setInterval(() => {
            const cy = cyRef.current;
            if (!cy || cy.destroyed() || document.hidden) return;
            tick += 1;
            cy.batch(() => {
                cy.edges('[?active]').forEach(edge => {
                    // 0.5 px per tick when idle-ish, up to ~3.5 px at hundreds of MB/s.
                    const speed = 0.5 + Math.min(3, Math.log10(1 + (Number(edge.data('bps')) || 0) / 1024) / 2);
                    edge.style('line-dash-offset', (edge.data('towardTarget') ? -1 : 1) * tick * speed);
                });
            });
        }, 50);
        return () => clearInterval(id);
    }, [cyRef]);

    const draw = useCallback(() => {
        const cy = cyRef.current;
        const canvas = canvasRef.current;
        const ctx = canvas?.getContext('2d');
        if (!cy || cy.destroyed() || !canvas || !ctx) { frameRef.current = undefined; return; }
        const dpr = window.devicePixelRatio || 1;
        const rect = canvas.getBoundingClientRect();
        if (canvas.width !== Math.round(rect.width * dpr)) { canvas.width = Math.round(rect.width * dpr); canvas.height = Math.round(rect.height * dpr); }
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, rect.width, rect.height);
        packetsRef.current = packetsRef.current.map(p => ({ ...p, progress: p.progress + 0.012 })).filter(p => p.progress < 1);
        for (const p of packetsRef.current) {
            const s = cy.getElementById(p.sourceId), t = cy.getElementById(p.targetId);
            if (s.empty() || t.empty()) continue;
            const a = s.renderedPosition(), b = t.renderedPosition();
            const x = a.x + (b.x - a.x) * p.progress, y = a.y + (b.y - a.y) * p.progress;
            const color = p.blocked ? FLOW_COLORS.blocked : FLOW_COLORS.allowed[dark ? 'dark' : 'light'];
            const tail = Math.max(0, p.progress - 0.08);
            ctx.globalAlpha = 0.35;
            ctx.strokeStyle = color;
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(a.x + (b.x - a.x) * tail, a.y + (b.y - a.y) * tail);
            ctx.lineTo(x, y);
            ctx.stroke();
            ctx.globalAlpha = 1;
            ctx.shadowBlur = p.blocked ? 12 : 8;
            ctx.shadowColor = color;
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(x, y, p.blocked ? 4 : 3, 0, 2 * Math.PI);
            ctx.fill();
            ctx.shadowBlur = 0;
        }
        frameRef.current = packetsRef.current.length ? requestAnimationFrame(draw) : undefined;
    }, [cyRef, canvasRef, dark]);

    useEffect(() => () => {
        if (frameRef.current !== undefined) cancelAnimationFrame(frameRef.current);
        frameRef.current = undefined;
    }, [draw]);

    /** Send a pulse from one node to another (ignored under reduced motion). */
    const pulse = useCallback((sourceId: string, targetId: string, blocked = false) => {
        if (prefersReducedMotion()) return;
        packetsRef.current = [...packetsRef.current, { sourceId, targetId, progress: 0, blocked }].slice(-50);
        if (frameRef.current === undefined) frameRef.current = requestAnimationFrame(draw);
    }, [draw]);

    return { pulse };
}
