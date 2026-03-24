import re

# Read the file
with open('services/apiService.ts', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the authFetch function
old_fn = '''// Helper for Authenticated Requests
export async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
    const token = localStorage.getItem('token');
    const headers = {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    } as HeadersInit;

    const response = await fetch(url, { ...options, headers });

    if (response.status === 401) {
        // Token expired or invalid
        localStorage.removeItem('token');
        window.location.href = '/login'; // Simple redirect
        throw new Error('Unauthorized');
    }

    return response;
}'''

new_fn = '''// Track active refresh request to prevent multiple simultaneous refreshes
let refreshPromise: Promise<string> | null = null;

// Helper function to refresh the access token
async function refreshAccessToken(): Promise<string> {
    // If already refreshing, return existing promise
    if (refreshPromise) return refreshPromise;
    
    refreshPromise = (async () => {
        try {
            const refreshToken = localStorage.getItem('refresh_token');
            
            if (!refreshToken) {
                throw new Error('No refresh token available');
            }
            
            const response = await fetch(`${API_BASE}/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: refreshToken })
            });
            
            if (!response.ok) {
                throw new Error('Failed to refresh token');
            }
            
            const data = await response.json();
            
            if (data.success && data.access_token) {
                localStorage.setItem('token', data.access_token);
                return data.access_token;
            }
            
            throw new Error('Invalid refresh response');
        } finally {
            // Clear the promise after completion
            refreshPromise = null;
        }
    })();
    
    return refreshPromise;
}

// Helper for Authenticated Requests
export async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
    const makeRequest = async (token: string | null) => {
        const headers = {
            'Content-Type': 'application/json',
            ...(options.headers || {}),
            ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        } as HeadersInit;

        return await fetch(url, { ...options, headers });
    };

    // First attempt with current token
    let token = localStorage.getItem('token');
    let response = await makeRequest(token);

    // If 401, try to refresh token and retry
    if (response.status === 401) {
        try {
            const newToken = await refreshAccessToken();
            response = await makeRequest(newToken);
        } catch (error) {
            // Refresh failed - clear storage and redirect to login
            localStorage.removeItem('token');
            localStorage.removeItem('refresh_token');
            window.location.href = '/login';
            throw new Error('Session expired');
        }
    }

    return response;
}'''

# Replace the function
content = content.replace(old_fn, new_fn)

# Write back
with open( 'services/apiService.ts', 'w', encoding='utf-8') as f:
    f.write(content)

print("Successfully updated authFetch function")
