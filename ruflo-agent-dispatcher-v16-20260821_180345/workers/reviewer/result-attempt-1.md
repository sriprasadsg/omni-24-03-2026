API service.ts read. Analyze file for correctness, maintainability, architecture consistency, error handling, observability, configuration, production risks. Prioritize findings. Next, other service files.
★ Insight ─────────────────────────────────────
`apiService.ts` contains a large number of API calls and related utility functions, making it a critical component for frontend-backend communication. Given its size and scope, thorough review of error handling, token refresh logic, and API consistency is essential for application stability and security.
─────────────────────────────────────────────────
Correctness:

*   Line 44-47, `normalizeSeverity`: Function attempts to normalize severity strings. If `severity` is not a string, it defaults to 'Low'. This implicit default might mask issues if severity data is unexpectedly malformed (e.g., `null`, `undefined`, or a number).
*   Line 108-114, `jwtSecondsUntilExpiry`: Returns `Infinity` on parsing error or missing `exp`. This could lead to tokens being treated as always valid, even if malformed or missing an expiry, creating a security risk (infinite session).
*   Line 193, `delayMs` calculation: `Math.max((secondsUntilExpiry - 300) * 1000, 5000)`. If `secondsUntilExpiry` is less than 300 (e.g., 200), `(secondsUntilExpiry - 300)` becomes negative (-100). The `Math.max` ensures a minimum delay of 5000ms. This is correct behavior, ensuring token refresh attempts are not too frequent, but the logic could be clearer with explicit checks for `secondsUntilExpiry <= 300` before calculation.

Maintainability:

*   Line 1-28 and 31-42: Large block of type imports. This indicates `types.ts` is a very large file, possibly a monolithic type definition. Large type files can make refactoring and understanding data structures difficult.
*   Line 266-290: Extensive global mutable state for various entities (USERS, ROLES, TENANTS, etc.). Direct manipulation of these global arrays (`USERS = [...USERS, createdUser]`) makes state management hard to track, debug, and test, especially in a concurrent environment or with complex UI interactions. Consider using a dedicated state management library (e.g., Redux, Zustand) or a more encapsulated pattern (e.g., React Context with `useReducer`) for better control and predictability.
*   Repetitive fetch pattern: Many functions follow `try...catch` with `authFetch`, `res.json()`, and `return []` on error. While consistent, this creates boilerplate. A higher-order function or a custom `useApi` hook could abstract this pattern.

Architecture Consistency:

*   Mix of direct `throw new Error(...)` and `console.error`/`console.warn` followed by `return []`/`null`. For example, `fetchSoftwareComponents` (L74) throws, while `fetchSboms` (L60) logs and returns empty array. This inconsistency in error propagation makes error handling unpredictable for callers.
*   `fetchWithCache` (L383-411) uses `sessionStorage` for caching. This is client-side only and not ideal for server-side rendering or for large datasets due to storage limits and blocking nature. The `updateLocalVar` callback directly mutates global state, coupling caching directly to global variables.

Error Handling:

*   `authFetch` (L214-263): Robust token refresh logic and session expiry handling on 401. This is good.
*   `console.error`/`console.warn` for API errors: Many API calls log errors to the console (e.g., L60, L66, L357, L363, L371, L377, L398, L575, L1002, L1007, L1031, L1044, L1050, L1055, L1066, L1077, L1090, L1103, L1114, L1127, L1138, L1149, L1165, L1178, L1210, L1243, L1258, L1302, L1313, L1336, L1347, L1421, L1435, L1446, L1457, L1470, L1481, L1496, L1509, L1525, L1536, L1549, L1564, L1575, L1586, L1599, L1612, L1627, L1639, L1656, L1677, L1689, L1720, L1731, L1784, L1816, L1846, L1871, L1888, L1915, L1926, L1959, L1979, L2004, L2015, L2023, L2033, L2041, L2048, L2060, L2073, L2084, L2094, L2106, L2118, L2128, L2138, L2147, L2156, L2165, L2174, L2183, L2190, L2198, L2205, L2214, L2225, L2233, L2242, L2249, L2257, L2265). While logging is good, in many cases, errors are silently caught and an empty array/null is returned (e.g., `fetchSoftwareComponents`, `fetchCloudAccounts`). This hides potential issues from upstream components that might expect an error for proper handling.
*   Login 429 rate limit: `login` (L566) throws a specific error "Too many login attempts". This is good for user feedback but should be consistent across all rate-limited endpoints.

Observability:

*   `console.error`/`warn` are used for logging. A more structured logging solution (e.g., Winston, Pino) with different levels (debug, info, warn, error) and potentially sending logs to a centralized system would improve observability.
*   No explicit tracing or correlation IDs are used for requests, making it hard to trace a request end-to-end through the system.

Configuration:

*   `API_BASE` (L51) is a hardcoded relative path. For more complex deployments or multi-environment setups, this might need to be configurable (e.g., via environment variables).

Production Risks:

*   Global mutable state: As mentioned in Maintainability, global arrays (USERS, ROLES, etc.) are a high risk in production for data integrity, race conditions, and difficult debugging.
*   `jwtSecondsUntilExpiry` returning `Infinity`: A malformed JWT could lead to an effectively infinite session, a severe security risk. This needs to be robustly handled to ensure proper token validation and expiry.
*   Inconsistent error handling: Silently returning empty arrays or nulls on API errors can lead to unexpected behavior in the UI without clear indicators of underlying problems, increasing the time to diagnose production issues.
*   Direct browser redirect (`window.location.href = '/login'`) in `_expireSession`: While intended for session expiry, this can be disruptive if triggered unexpectedly or during background operations.

Findings:

1.  **Security/Correctness**: `jwtSecondsUntilExpiry` (L106-114) returns `Infinity` on parsing errors/missing `exp`. This can lead to tokens being treated as perpetually valid, a critical security vulnerability. Fix: return 0 or a negative value (already expired) on error, forcing re-authentication.
2.  **Maintainability/Architecture**: Extensive global mutable state (L266-290, USERS, ROLES, etc.). Violates predictable state flow, complicates debugging, and introduces concurrency risks. Fix: Encapsulate state using a dedicated store or local component state.
3.  **Architecture Consistency/Error Handling**: Inconsistent error propagation (L74 throws, L60 logs/returns empty). Callers cannot reliably predict error handling, making robust error handling difficult. Fix: Standardize error handling: either always throw, or always return a structured error object.
4.  **Observability**: Reliance on `console.error`/`warn` for critical backend issues. Lacks structured logging, centralized aggregation, and tracing. Fix: Implement a structured logging solution (e.g., an `ErrorService`) to provide context-rich logs for easier debugging and monitoring.
5.  **Correctness/Reliability**: `normalizeSeverity` (L44-47) defaults to 'Low' for non-string input. This could mask actual severity issues if the input is malformed, leading to incorrect risk assessment. Fix: Explicitly handle non-string inputs (e.g., throw error, return 'Unknown', or log a warning if data integrity cannot be guaranteed).

Next, read `geminiService.ts`.
