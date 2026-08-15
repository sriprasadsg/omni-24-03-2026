# Coding Conventions

**Analysis Date:** 2026-08-12

## Naming Patterns

**Files:**
- [FeatureScoped]: *.tsx or *.ts for components (e.g., 'UserManagementModal.tsx')
- [Service]: *.ts for service implementations (e.g., 'apiService.ts')

**Functions:**
- [CamelCase]: Functions with primary camelCase naming patterns observed ('renderPaginatedTable', 'fetchWithRetry')
- [PascalCase]: React components follow PascalCase naming conventions ('UserManagementModal')

**Variables:**
- [CamelCase]: Consistent camelCase usage for variables, consistent with function naming
- [PascalCase]: Used for class names and React component props where appropriate

**Types:**
- [PascalCase]: TypeScript interface names follow PascalCase (e.g., 'UserVerificationStatus', 'VerificationResult')
- [CamelCase]: Type aliases where appropriate for brevity

## Code Style

**Formatting:**
- Vite-configured React application follows standard ESLint configuration
- No explicit formatting rules detected beyond standard React conventions
- Prettier integration likely configured but not directly visible in file listings

**Linting:**
- ESLint 10.8.0 configured in `eslint.config.js`
- Key rules off by default: 
  - `@typescript-eslint/no-explicit-any` → 'off'
  - `@typescript-eslint/no-unused-vars` → 'off'
- Custom rule overrides for React state management and testing patterns

**Import Organization:**
- Articles suggests strict import ordering based on module categories
- Path aliasing likely configured through Vite resolvers (inferred from imports in routes.tsx)
- No explicit ordering rules present in scanned configs

## Error Handling

**Patterns:**
- Service methods return error objects rather than throwing exceptions
- Error states managed via React contexts and displayed via toast notifications
- API error responses handled with standardized error object extraction

## Logging

**Framework:** toast notifications for user-facing logging
**Patterns:** 
- Generic `showToast` function used in test mocks (from ITAMConsole.test.tsx)
- Error details not exposed publicly, suggesting user-friendly error messaging

## Function Design

**Size:** Modular function design with small, focused functions
**Parameters:** Functions typically accept 1-3 parameters for clarity
**Return Values:** Consistent return types per service interface; often single object responses rather than partial data

## Module Design

**Exports:** Named exports across the codebase
**Barrel Files:** No explicit barrel files (.barrel) detected in project structure; likely using direct path imports

---  
*Convention analysis: 2026-08-12*