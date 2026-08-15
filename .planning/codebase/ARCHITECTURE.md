<!-- refreshed: 2026-08-12 -->
# Architecture

**Analysis Date:** 2026-08-12

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│                       React Application                        │
├──────────────────┬──────────────────┬───────────────────────┤
│   UI Components  │     Contexts     │    Routing/Lazy       │
│ `[components/]`  │ `[contexts/]`    │  `[router/routes.tsx]`│
└────────┬─────────┴────────┬─────────┴──────────┬────────────┘
         │                  │                     │
         ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    Services & API                           │
│        `[services/apiService.ts]`                           │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                   External Integrations                    │
│  Socket.io, WebAuthn, DOMPurify, Axios, etc.               │
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| UI Layer | Renders application interface | `[components/*/].tsx` |
| Context Layer | Manages application state | `[contexts/*/].tsx` |
| API Layer | Handles backend communication | `[services/apiService.ts]` |
| Routing | Manages navigation and lazy loading | `[src/router/routes.tsx]` |

## Pattern Overview

**Overall:** Large-scale enterprise dashboard application with component-based architecture

**Key Characteristics:**
- Extensive component library (~100+ components)
- Context-based state management
- Lazy loading for performance
- Real-time updates via WebSockets
- Strong emphasis on security (XSS protection, WebAuthn)
- Comprehensive testing with Vitest

## Layers

**Presentation Layer:**
- Purpose: User interface and interactions
- Location: `components/`
- Contains: All React components (dashboards, modals, tables, charts)
- Depends on: Contexts, Services
- Used by: Application routes

**State Management Layer:**
- Purpose: Global application state and side effects
- Location: `src/contexts/`
- Contains: ThemeProvider, FeaturesContext, UserContext, etc.
- Depends on: None within application
- Used by: All components

**Data Layer:**
- Purpose: Backend API communication
- Location: `src/services/apiService.ts`
- Contains: All API service definitions and HTTP clients
- Depends: axios, environment configuration
- Used by: Components via hooks

**External Integration Layer:**
- Purpose: Third-party services and libraries
- Location: Throughout codebase (import statements)
- Contains: Socket.io, @simplewebauthn/browser, DOMPurify, recharts, cytoscape, xterm
- Depends: npm packages
- Used by: Various components

## Data Flow

### Primary Request Path

1. User interaction with UI (`[components/*/].tsx`) at line X
2. Component calls service APIs (`src/services/apiService.ts`) line Y
3. Response returned to component and rendered to user

### Real-time Updates

1. WebSocket connection established via `socket.io-client`
2. Socket.io listener receives real-time data
3. State updates trigger component re-renders via React context

## Key Abstractions

**Lazy Loading:**
- Purpose: Performance optimization by loading routes only when needed
- Examples: `src/router/routes.tsx` lazy imports
- Pattern: `React.lazy(() => import('...'))` with fallback loading

**Context-Based State:**
- Purpose: Global state management without prop drilling
- Examples: `src/contexts/UserContext.tsx`, `src/contexts/ThemeProvider.tsx`
- Pattern: React Context API with custom hooks

**Service Layer:**
- Purpose: Centralized API communication
- Examples: `src/services/apiService.ts`
- Pattern: axios-based HTTP client with centralized error handling

## Entry Points

**Application Entry Point:**
- Location: Not explicitly defined in scanned files, likely `src/main.tsx` or similar
- Triggers: Vite dev server or build process
- Responsibilities: Renders React application with all providers

## Architectural Constraints

- **Threading:** Single-threaded JavaScript (browser environment)
- **Global state:** Managed via React contexts, potentially multiple context providers
- **Circular imports:** Avoided through lazy loading and service layers
- **Bundle size:** Mitigated via lazy loading of ~100+ components

## Anti-Patterns

### Component Monolith
**What happens:** Large components that combine multiple responsibilities
**Why it's wrong:** Difficult to test, maintain, and reuse
**Do this instead:** Break into smaller, focused components with clear responsibilities

### Direct State Sharing
**What happens:** Components sharing state through intermediate components instead of contexts
**Why it's wrong:** Prop drilling makes code complex and error-prone
**Do this instead:** Use React Context for global state that needs to be shared

## Error Handling

**Strategy:** Try-catch blocks at API boundaries with user-facing error messages
**Patterns:** Service methods return error objects, UI components display toast notifications

## Cross-Cutting Concerns

**Logging:** Implemented via toast notifications and potential service error responses
**Validation:** Client-side validation in components, server-side validation via API
**Authentication:** WebAuthn via @simplewebauthn/browser, JWT via UserContext

---

*Architecture analysis: 2026-08-12*
