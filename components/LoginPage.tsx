import React, { useState, useEffect } from 'react';
import { useUser } from '../contexts/UserContext';
import { BotIcon, MailIcon, KeyIcon } from './icons';
import { User } from '../types';
import { SignupForm } from './SignupForm';
import MFAVerifyModal from './MFAVerifyModal';
import * as api from '../services/apiService';

interface LoginPageProps {
    users: User[];
    onLogin?: (email: string, password: string) => Promise<boolean>;
    onSignup?: (data: any) => Promise<boolean>;
}

export const LoginPage: React.FC<LoginPageProps> = ({ users, onLogin, onSignup }) => {
    const { login: contextLogin, signup } = useUser();
    const [showSignup, setShowSignup] = useState(false);
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState(() => {
        // Show SSO error from URL param (e.g. ?error=sso_not_registered)
        const params = new URLSearchParams(window.location.search);
        const e = params.get('error');
        if (e === 'sso_not_registered') return 'This email is not registered. Please sign up first.';
        if (e === 'sso_failed') return 'Google sign-in failed. Please try again.';
        if (e === 'invalid_state') return 'Authentication session expired. Please try again.';
        return '';
    });
    const [isLoading, setIsLoading] = useState(false);
    const [mfaSessionToken, setMfaSessionToken] = useState<string | null>(null);
    const [ssoEnabled, setSsoEnabled] = useState(false);

    useEffect(() => {
        api.fetchSsoProviders().then((p: any) => {
            setSsoEnabled(Array.isArray(p?.providers) && p.providers.length > 0);
        }).catch(() => {});
    }, []);

    const handleMfaSuccess = (_accessToken: string, _user: any) => {
        // Token already stored by MFAVerifyModal — reload so App.tsx restoreSession picks it up
        window.location.reload();
    };

    const handleSignup = async (data: { companyName: string; name: string; email: string; password: string }) => {
        const success = onSignup ? await onSignup(data) : await signup(data);
        if (success) {
            // Auto-login after successful signup (requires backend flow, simple context mock for now)
            // await login(data.email, data.password);
            window.location.reload();
        }
        return success;
    };

    const handleLogin = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setIsLoading(true);

        try {
            const data = await api.login(email, password);

            // Two-phase MFA login: password verified, TOTP challenge next
            if (data.mfa_required && data.mfa_session_token) {
                setMfaSessionToken(data.mfa_session_token);
                return;
            }

            // Normal login (no MFA) — let App.tsx handle state setup
            if (onLogin) {
                await onLogin(email, password);
            } else {
                window.location.reload();
            }

        } catch (err) {
            console.error('Login error:', err);
            setError('Invalid email or password.');
        } finally {
            setIsLoading(false);
        }
    };

    if (mfaSessionToken) {
        return (
            <MFAVerifyModal
                mfaSessionToken={mfaSessionToken}
                onSuccess={handleMfaSuccess}
                onCancel={() => { setMfaSessionToken(null); setIsLoading(false); }}
            />
        );
    }

    if (showSignup) {
        return <SignupForm onSignup={handleSignup} onSwitchToLogin={() => setShowSignup(false)} />;
    }

    return (
        <div className="min-h-screen flex flex-col justify-center items-center p-4 relative overflow-hidden">
            {/* Animated Background Blobs */}
            <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-primary-500/20 rounded-full blur-[120px] animate-pulse pointer-events-none"></div>
            <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-purple-600/20 rounded-full blur-[120px] animate-pulse pointer-events-none" style={{ animationDelay: '2s' }}></div>

            <div className="w-full max-w-md z-10 fade-in">
                {/* Header */}
                <div className="text-center mb-8">
                    <BotIcon className="text-primary-400 mx-auto drop-shadow-[0_0_10px_rgba(0,210,255,0.5)]" size={64} />
                    <h1 className="text-3xl font-bold mt-4 text-white drop-shadow-md">
                        Enterprise Omni-Agent
                    </h1>
                    <p className="text-sm text-gray-300 mt-2">
                        Future-Ready AI Platform
                    </p>
                </div>

                {/* Login Form */}
                <div className="glass-panel rounded-xl p-8 backdrop-blur-xl">
                    <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-6">
                        Sign In
                    </h2>

                    <form onSubmit={handleLogin} className="space-y-6">
                        {/* Email Field */}
                        <div>
                            <label htmlFor="email" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                Email Address
                            </label>
                            <div className="relative">
                                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                    <MailIcon size={20} className="text-gray-400" />
                                </div>
                                <input
                                    id="email"
                                    type="email"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    required
                                    className="block w-full pl-10 pr-3 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                                    placeholder="Enter your email"
                                    autoComplete="email"
                                />
                            </div>
                        </div>

                        {/* Password Field */}
                        <div>
                            <label htmlFor="password" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                Password
                            </label>
                            <div className="relative">
                                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                    <KeyIcon size={20} className="text-gray-400" />
                                </div>
                                <input
                                    id="password"
                                    type="password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    required
                                    className="block w-full pl-10 pr-3 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                                    placeholder="Enter your password"
                                    autoComplete="current-password"
                                />
                            </div>
                        </div>

                        {/* Error Message */}
                        {error && (
                            <div className="p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg">
                                <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
                            </div>
                        )}

                        {/* Login Button */}
                        <button
                            type="submit"
                            disabled={isLoading}
                            className="w-full py-3 px-4 bg-gradient-to-r from-flash-blue to-flash-purple hover:from-cyan-400 hover:to-purple-500 disabled:opacity-50 text-white font-bold rounded-xl shadow-lg shadow-flash-blue/30 transition-all transform hover:scale-[1.02] active:scale-[0.98] outline-none"
                        >
                            {isLoading ? 'Signing in...' : 'Sign In'}
                        </button>
                    </form>

                    {/* SSO Divider + Google button */}
                    {ssoEnabled && (
                        <>
                            <div className="mt-5 relative">
                                <div className="absolute inset-0 flex items-center">
                                    <div className="w-full border-t border-gray-300 dark:border-gray-600"></div>
                                </div>
                                <div className="relative flex justify-center text-sm">
                                    <span className="px-2 bg-white dark:bg-gray-800 text-gray-500 dark:text-gray-400">or continue with</span>
                                </div>
                            </div>
                            <a
                                href="/api/sso/google/login"
                                className="mt-4 w-full flex items-center justify-center gap-3 py-3 px-4 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-200 font-medium hover:bg-gray-50 dark:hover:bg-gray-600 transition-all"
                            >
                                <svg className="w-5 h-5" viewBox="0 0 24 24">
                                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                                    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
                                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                                </svg>
                                Sign in with Google
                            </a>
                        </>
                    )}

                    {/* Divider */}
                    <div className="mt-6 relative">
                        <div className="absolute inset-0 flex items-center">
                            <div className="w-full border-t border-gray-300 dark:border-gray-600"></div>
                        </div>
                        <div className="relative flex justify-center text-sm">
                            <span className="px-2 bg-white dark:bg-gray-800 text-gray-500 dark:text-gray-400">
                                Don't have an account?
                            </span>
                        </div>
                    </div>

                    {/* Signup Link */}
                    <button
                        onClick={() => setShowSignup(true)}
                        className="mt-4 w-full py-3 px-4 bg-gray-100 hover:bg-gray-200 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-800 dark:text-white font-medium rounded-lg transition-all"
                    >
                        Create New Account
                    </button>
                </div>

                {/* Demo Credentials Info */}
                <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
                    <p className="text-xs text-blue-800 dark:text-blue-300 font-semibold mb-2">Demo Credentials:</p>
                    <div className="space-y-1 text-xs text-blue-700 dark:text-blue-400">
                        <p>• Super Admin: <span className="font-mono">super@omni.ai</span></p>
                        <p>• Tenant Admin: <span className="font-mono">admin@acmecorp.com</span></p>
                        <p>• Security Analyst: <span className="font-mono">analyst@acmecorp.com</span></p>
                        <p className="mt-2 text-blue-600 dark:text-blue-500">Password: Check user data or use signup</p>
                    </div>
                </div>
            </div>
        </div>
    );
};
