# Design System Master File — Spatial Glass (2030)

> Source of truth for the Omni-Agent AI UI from 2026-10-19. Supersedes
> `design-system/enterprise-omniagent/MASTER.md` (Aug 2026, "Trust & Authority").
> Page overrides go in `design-system/omni-agent-2030/pages/<page>.md`.

**Direction:** Spatial Glass — dark first (visionOS-like): a deep-space canvas lit by
soft ambient light, layered frosted surfaces, and one electric-cyan accent reserved
for focus, active and live states. Light mode is fully supported. No violet/purple as
a brand colour (rejected for enterprise B2B in Aug 2026).

## Tokens (index.css, consumed through tailwind.config.js)

| Token | Value | Use |
|---|---|---|
| `--primary-400` | `#22D3EE` | Dark-mode accent text, active nav, glows |
| `--primary-500` | `#0891B2` | Icons, rings, borders (reads on both themes) |
| `--primary-600` | `#0E7490` | Primary buttons (white text 5.4:1) |
| `--space-950` | `#060A14` | Dark canvas |
| `--space-800` | `#161E30` | Dark cards (`dark:bg-gray-800`) |
| `--space-500` | `#637089` | Secondary text (4.9:1 on white) |
| canvas (light) | `#F3F6FA` | Light canvas |

`gray`, `slate` and `secondary` all map to the `space` ramp; ramps are RGB triplets
so opacity modifiers (`bg-primary-500/10`) work. Blue stays Tailwind's default
(pairs with cyan); red/amber/green stay semantic.

## Type
Inter variable (opsz 14–32, wght 300–800), features `cv02 cv03 cv04 cv11 ss01`,
tabular numerals in tables. Monospace: JetBrains Mono.

## Surfaces & depth
- `.glass` / `.glass-panel` / `.glass-strong`: frosted panes (blur 20–24px). Used for
  the floating sidebar (rounded-3xl), header (rounded-2xl) and modals (rounded-3xl).
- Cards stay solid (no per-card blur, for performance) with a lit top edge in dark mode.
- Radii: lg 10px, xl 14px, 2xl 20px, 3xl 28px.
- Ambient light: fixed `body::before` radial gradients (cyan top-left, blue bottom-right).

## Interaction
- One visible focus ring everywhere (`:focus-visible`, 2px `--focus-ring`, offset 2).
- Primary buttons glow softly in dark mode; motion 150–360ms, expo-out easing;
  `prefers-reduced-motion` and `forced-colors` respected.
- Shell: floating sidebar + header with breadcrumb (section / page) and an
  "Ask AI or run a command… ⌘K" omnibox; search is an icon button (⌘/).

## Anti-patterns
Fake status indicators, violet brand colour, per-element backdrop blur on large
lists, hard-coded rgba/hex in components (use tokens), text under 4.5:1.
