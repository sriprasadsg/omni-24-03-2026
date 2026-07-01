# Performance Metrics Frontend Fix Summary

## Problem Diagnosis

**Root Cause**: Health check endpoint mismatch
- Frontend: Calling `/api/health` via `apiService.ts` line 190
- Backend proxy: Vite configured to proxy `/health` → `http://127.0.0.1:5000`
- Result: Health check hits `/api/health` which may not exist or times out

## Solution

The health check in `apiService.ts` is using:
```typescript
const healthUrl = `${API_BASE}/health?t=${Date.now()}`;
```

Where `API_BASE = 'http://127.0.0.1:5000/api'`

This resolves to: `http://127.0.0.1:5000/api/health`

However, the Vite proxy is configured for bare `/health

` NOT `/api/health`.

**Fix Options**:
1. Change frontend to use `/health` instead of `${API_BASE}/health`
2. Add `/api/health` endpoint to backend
3. Update Vite proxy to handle both `/health` and `/api/health`

## Recommended Fix
Option 1: Update frontend health check to use correct endpoint path.
