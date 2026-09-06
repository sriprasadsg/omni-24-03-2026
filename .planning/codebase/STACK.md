# Technology Stack

**Analysis Date:** 2026-08-12

## Languages

**Primary:**
- TypeScript ~5.7 - Used for all application code (`.ts`, `.tsx`).
- JavaScript (ESM) - Project is configured with `"type": "module"`.

**Secondary:**
- Shell - Used for scripts.

## Runtime

**Environment:**
- Node.js >=20

**Package Manager:**
- npm (implied by `package.json`, but no `package-lock.json` is visible in listings)
- Lockfile: not detected

## Frameworks

**Core:**
- React 19.2.0 - For UI components.
- Vite 8.0.14 - As the frontend build tool and dev server.

**Testing:**
- Vitest 3.2.4 - Test runner and framework.
- React Testing Library 16.3.0 - For testing React components.

**Build/Dev:**
- Vite 8.0.14 - Handles development server and production builds.
- TypeScript ~5.7 - For type-checking and transpilation.
- ESLint 10.8.0 - For linting.
- PostCSS 8.4.35 / Tailwind CSS 3.4.17 - For CSS processing.

## Key Dependencies

**Critical:**
- `react` 19.2.0 - Core UI library.
- `vite` 8.0.14 - Core tooling for development and building.
- `vitest` 3.2.4 - Core testing framework.

**Infrastructure:**
- `axios` 1.13.2 - For making HTTP requests.
- `socket.io-client` 4.7.2 - For WebSocket communication.
- `reactflow` 11.11.4 - For building node-based editors and diagrams.
- `xterm` 5.3.0 - For terminal emulation in the browser.
- `recharts` 3.5.1 - For charting.

## Configuration

**Environment:**
- Not detected, likely through `.env` files which are not read.

**Build:**
- `vite.config.ts` - Main Vite configuration.
- `tsconfig.json` - TypeScript compiler options.
- `postcss.config.js` - PostCSS configuration.
- `tailwind.config.js` - Tailwind CSS configuration.
- `eslint.config.js` - ESLint configuration.

## Platform Requirements

**Development:**
- Node.js version 20 or higher.
- An `npm`-compatible package manager.

**Production:**
- Deployment target is a static file host serving the output of `vite build`.

---

*Stack analysis: 2026-08-12*
