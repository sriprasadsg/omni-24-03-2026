// Helper to generate SVG Data URIs for Cytoscape from Lucide icon names/colors
export const getIconDataUri = (type: string, color: string = '%233b82f6') => {
    // Basic SVG templates for common network icons
    let svgPath = '';
    // SVG Paths for: cloud, shield, server, router, layers (switch), monitor (endpoint)
    if (type === 'cloud') svgPath = 'M17.5 19c.5 0 1-.1 1.5-.3 2-1 3.5-3 3.5-5.2 0-3.3-2.7-6-6-6-.3 0-.7 0-1 .1C14.4 5.3 12.4 4 10 4 6.1 4 3 7.1 3 11c0 .4 0 .7.1 1.1C1.9 12.8 1 14.3 1 16c0 2.2 1.8 4 4 4h12.5';
    else if (type === 'shield') svgPath = 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z';
    else if (type === 'server') svgPath = 'M2 10V6a2 2 0 012-2h16a2 2 0 012 2v4M2 14v4a2 2 0 002 2h16a2 2 0 002-2v-4M6 6h.01M6 18h.01';
    else if (type === 'router') svgPath = 'M2 13v6a2 2 0 002 2h16a2 2 0 002-2v-6M12 3v10M12 3l-4 4M12 3l4 4';
    else if (type === 'switch' || type === 'layers' || type === 'subnet') svgPath = 'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5';
    else svgPath = 'M4 6a2 2 0 012-2h12a2 2 0 012 2v7a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 20h-4M12 15v3';

    return `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${type === 'server' ? '<rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect><rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect><line x1="6" y1="6" x2="6.01" y2="6"></line><line x1="6" y1="18" x2="6.01" y2="18"></line>' : `<path d="${svgPath}"></path>`}</svg>`;
};

export const stylesheet = [
    {
        selector: 'node',
        style: {
            'label': 'data(label)',
            'text-valign': 'bottom',
            'text-halign': 'center',
            'font-size': '10px',
            'color': '#8e949e',
            'font-family': 'JetBrains Mono, monospace',
            'text-margin-y': 6,
            'background-color': '#1a1f26',
            'width': 44,
            'height': 44,
            'border-width': 2,
            'border-color': '#3b82f6',
            'background-image': (ele: any) => getIconDataUri(ele.data('icon') || 'monitor'),
            'background-fit': 'contain',
            'background-clip': 'none',
            'background-width': '65%',
            'background-height': '65%',
            'background-position-x': '50%',
            'background-position-y': '50%'
        }
    },
    {
        selector: ':parent',
        style: {
            'background-opacity': 0.08,
            'background-color': '#1e293b',
            'border-color': '#334155',
            'border-width': 1,
            'border-style': 'solid',
            'text-valign': 'top',
            'text-halign': 'center',
            'text-margin-y': -10,
            'font-weight': 'bold',
            'font-size': '11px',
            'color': '#475569',
            'text-transform': 'uppercase',
            'letter-spacing': '0.1em'
        }
    },
    {
        selector: 'node[type = "cloud"]',
        style: { 'border-color': '#8b5cf6', 'background-image': (ele: any) => getIconDataUri('cloud', '%238b5cf6') }
    },
    {
        selector: 'node[type = "firewall"]',
        style: { 'border-color': '#f43f5e', 'background-image': (ele: any) => getIconDataUri('shield', '%23f43f5e') }
    },
    {
        selector: 'node[icon = "server"]',
        style: { 'border-color': '#0ea5e9', 'background-image': (ele: any) => getIconDataUri('server', '%230ea5e9') }
    },
    {
        selector: 'node[status = "down"]',
        style: { 'border-color': '#ef4444', 'border-opacity': 0.5, 'opacity': 0.6 }
    },
    {
        selector: 'node[isVlan = true]',
        style: {
            'background-opacity': 0.1,
            'background-color': '#6366f1',
            'border-color': '#818cf8',
            'border-width': 1.5,
            'border-style': 'solid',
            'text-valign': 'top',
            'text-halign': 'center',
            'text-margin-y': 5,
            'font-size': '10px',
            'font-weight': 'bold',
            'color': '#c7d2fe',
            'padding': '30px'
        }
    },
    {
        selector: 'edge',
        style: {
            'width': 1.5,
            'line-color': '#1e293b',
            'target-arrow-color': '#1e293b',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            'opacity': 0.6
        }
    }
];
