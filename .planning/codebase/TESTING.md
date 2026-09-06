# Testing Patterns

**Analysis Date:** 2026-08-12

## Test Framework

**Runner:**
- Vitest 3.2.4 - Test runner and framework.
- Config: From `vite.config.ts` testing section.

**Run Commands:**
```bash
npm run test              # Run all tests
npm run test:watch        # Watch mode
```

## Test File Organization

**Location:**
- Co-located with components under `components/`
- Explicitly placed in `src/__tests__/` for integration/smoke tests
- File naming: Either `*.test.tsx` or `*.spec.tsx`
- Test files primarily target React components

**Naming:**
- [Descriptive]: `ITAMConsole.test.tsx`, `EvidenceMarkdownViewer.test.tsx`
- [Component/Test Pattern]: `<ComponentName>.test.tsx`

**Structure:**
```
[Component/Test].test.tsx
```

## Test Structure

**Suite Organization:**
```typescript
describe('ComponentName', () => {
  // Test cases
});

// Examples observed:
// - Multiple describe blocks per file
// - Nested describe blocks for feature-specific testing
// - Test cases grouped by functionality (rendering, interaction, edge cases)
```

**Patterns Observed:**
- Mock external dependencies (e.g., axios, dompurify)
- Use vi.mock() for mocking implementations
- Setup async tests with waitFor()
- Mock Window properties for error testing
- Snapshot testing not observed - focus on behavior testing

## Mocking

**Framework:** Vitest mocking utilities
**Patterns:**
```typescript
vi.mock('dependency', () => ({
  __esModule: true,
  default: mockFunctionality
}));

// Examples:
// - dompurify mocking in EvidenceMarkdownViewer.test.tsx
// - axios mocking in ITAMConsole.test.tsx
// - jest-like mock functions via vi.fn()
//   (mocked in ITAMConsole.test.tsx for services)

// What to Mock:
// - External API calls (axios)
// - Third-party libraries (dompurify)
// - Helper functions where needed for determinism

## Fixtures and Factories

**Test Data:**
[Show pattern from test files]

**Location:**
- Test files themselves contain test data fixtures
- Data typically lightweight JSON objects
- Examples:
```typescript
const SAFE_EVIDENCE = {
  id: 'ev-001',
  name: 'CVE-2024-0001 scan result',
  content: '## Summary\n\nNo critical findings.',
};
const XSS_EVIDENCE = {
  id: 'ev-002',
  name: 'Malicious evidence',
  content: '<script>...</script><img onerror="window.__xss=true" src="x"/>',
};

// Where fixtures live:
- Directly in test files alongside test cases
```

## Test Types

**Unit Tests:**
- Focus on isolated component behavior
- Mocking of external dependencies
- Testing rendering output and interactions

**Integration Tests:**
- Focus on component interaction with services
- Service layer is heavily mocked
- Tests complete UI integration flows

**E2E Tests:**
- Not detected in project (structure suggests unit/integration focus)
- Mocked environment for browser APIs

## Coverage

**Requirements:** No specific coverage threshold mandated (not detected)
**View Coverage:**
```bash
npm run test with proper Vitest configuration
```

## Common Patterns

**Async Testing:**
```typescript
// From observed tests:
// await waitFor(() => {
  // Expectation on mocked API calls
});
```

**Error Testing:**
```typescript
// Mock responses to simulate error states
// tested via expectation on mocked service
const fetchMock = vi.fn().mockRejectedValue({ response: { status: 404 } });
```

**Setup Pattern:**
- Global setup in `setup.ts` (imports for testing utilities)
- Component-specific setup via imports in test files

**Teardown Pattern:**
- Automatic cleanup by Vitest
- Manual cleanup via vi.cleanup() when needed

**Screen Utilities:**
- From '@testing-library/react' used for:
  - Rendering (`render(<Component />)`)
  - Querying (`screen.getByText()`)
  - Event simulation (`fireEvent.click()`)

---

*Testing analysis: 2026-08-12*