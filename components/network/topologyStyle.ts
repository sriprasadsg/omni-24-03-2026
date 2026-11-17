// Cytoscape stylesheet and layout for the Network Topology map, in both themes.
// Role hues are the dataviz reference slots 1-3 (blue, orange, aqua), which pass the all-pairs
// colour-vision checks; every other device stays neutral and is told apart by its icon and label.

export type RoleGroup = 'internet' | 'perimeter' | 'server' | 'device';

export const roleGroup = (d: any): RoleGroup => {
    if (!d) return 'device';
    if (d.type === 'cloud' || d.zone === 'Internet') return 'internet';
    if (d.zone === 'Perimeter' || d.role === 'Gateway') return 'perimeter';
    if (d.role === 'Server') return 'server';
    return 'device';
};

const ROLE_HEX: Record<'light' | 'dark', Record<RoleGroup, string>> = {
    light: { internet: '#2a78d6', perimeter: '#eb6834', server: '#1baf7a', device: '#637089' },
    dark: { internet: '#3987e5', perimeter: '#d95926', server: '#199e70', device: '#8F9BB0' },
};

export const ROLE_LEGEND: { group: RoleGroup; label: string; swatch: string }[] = [
    { group: 'internet', label: 'Internet', swatch: 'border-[#2a78d6] dark:border-[#3987e5]' },
    { group: 'perimeter', label: 'Perimeter', swatch: 'border-[#eb6834] dark:border-[#d95926]' },
    { group: 'server', label: 'Server', swatch: 'border-[#1baf7a] dark:border-[#199e70]' },
    { group: 'device', label: 'Other device', swatch: 'border-[#637089] dark:border-[#8F9BB0]' },
];

const CRITICAL = '#d03b3b';
export const FLOW_COLORS = { allowed: { light: '#0891B2', dark: '#22D3EE' }, blocked: CRITICAL };

// Lucide shapes (cloud, shield, server, layers, printer, monitor) as Cytoscape background images.
const ICON_SVG: Record<string, string> = {
    cloud: '<path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/>',
    shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>',
    server: '<rect width="20" height="8" x="2" y="2" rx="2"/><rect width="20" height="8" x="2" y="14" rx="2"/><path d="M6 6h.01M6 18h.01"/>',
    layers: '<path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>',
    printer: '<path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><path d="M6 9V3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v6"/><rect x="6" y="14" width="12" height="8" rx="1"/>',
    monitor: '<rect width="20" height="14" x="2" y="3" rx="2"/><path d="M8 21h8M12 17v4"/>',
};

export const iconUri = (icon: string | undefined, color: string) => {
    const body = ICON_SVG[icon === 'laptop' || !icon || !ICON_SVG[icon] ? 'monitor' : icon];
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
    return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
};

// animate: 'end' computes positions synchronously and animates through the core loop, which
// cy.destroy() stops; a per-frame layout keeps touching a destroyed renderer after a remount.
export const TOPOLOGY_LAYOUT = {
    name: 'cose-bilkent',
    animate: 'end',
    animationDuration: 400,
    fit: true,
    padding: 48,
    nodeDimensionsIncludeLabels: true,
    idealEdgeLength: 70,
    nodeRepulsion: 4500,
    nestingFactor: 0.1,
    gravity: 0.4,
    gravityCompound: 1.0,
    gravityRangeCompound: 1.5,
    tile: true,
};

export const topologyStylesheet = (dark: boolean): any[] => {
    const mode = dark ? 'dark' : 'light';
    const t = dark
        ? { node: '#161E30', label: '#A9B3C6', zone: '#FFFFFF', zoneOpacity: 0.025, zoneBorder: '#8F9BB0', edge: '#8F9BB0', accent: '#22D3EE', textBg: '#0C1322' }
        : { node: '#FFFFFF', label: '#46526A', zone: '#637089', zoneOpacity: 0.04, zoneBorder: '#8F9BB0', edge: '#8F9BB0', accent: '#0891B2', textBg: '#F3F6FA' };
    const roleColor = (ele: any) => ROLE_HEX[mode][roleGroup(ele.data())];
    return [
        {
            selector: 'core',
            style: { 'active-bg-color': t.accent, 'active-bg-opacity': 0.08, 'selection-box-color': t.accent, 'selection-box-opacity': 0.08 },
        },
        {
            selector: 'node',
            style: {
                label: 'data(label)',
                'text-wrap': 'wrap',
                'text-max-width': '140px',
                'text-valign': 'bottom',
                'text-halign': 'center',
                'text-margin-y': 6,
                'font-size': 12,
                'font-family': 'Inter, system-ui, sans-serif',
                'line-height': 1.3,
                color: t.label,
                'text-background-color': t.textBg,
                'text-background-opacity': 0.8,
                'text-background-padding': '2px',
                'text-background-shape': 'roundrectangle',
                shape: 'round-rectangle',
                width: 40,
                height: 40,
                'background-color': t.node,
                'border-width': 1.5,
                'border-color': roleColor,
                'background-image': (ele: any) => iconUri(ele.data('icon'), roleColor(ele)),
                'background-width': '55%',
                'background-height': '55%',
                'background-clip': 'none',
                'overlay-opacity': 0,
                'transition-property': 'opacity, border-width',
                'transition-duration': 150,
            },
        },
        {
            selector: 'node[status = "Down"], node[status = "down"]',
            style: { 'border-style': 'dashed', 'border-color': CRITICAL, 'border-width': 2 },
        },
        {
            selector: ':parent',
            style: {
                shape: 'round-rectangle',
                'background-image': 'none',
                'background-color': t.zone,
                'background-opacity': t.zoneOpacity,
                'border-width': 1,
                'border-style': 'dashed',
                'border-color': t.zoneBorder,
                'border-opacity': 0.45,
                'text-valign': 'top',
                'text-halign': 'center',
                'text-margin-y': -4,
                'font-size': 11,
                'font-weight': 600,
                'text-transform': 'uppercase',
                'text-background-opacity': 0,
                padding: '24px',
            },
        },
        {
            selector: 'node[?isVlan]',
            style: { 'background-color': t.accent, 'background-opacity': 0.06, 'border-style': 'solid', 'border-color': t.accent, 'border-opacity': 0.5 },
        },
        {
            selector: 'edge',
            style: { width: 1.5, 'line-color': t.edge, 'line-opacity': 0.45, 'curve-style': 'bezier', 'overlay-opacity': 0 },
        },
        { selector: 'node:selected', style: { 'border-width': 3, 'border-color': t.accent, 'border-style': 'solid', 'background-color': t.node } },
        { selector: '.faded', style: { opacity: 0.18 } },
        { selector: 'edge.hl', style: { 'line-color': t.accent, 'line-opacity': 0.9, width: 2.5 } },
    ];
};
