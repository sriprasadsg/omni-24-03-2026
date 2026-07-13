import React, { useState, useEffect } from 'react';
import { startAuthentication } from '@simplewebauthn/browser';
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

    const handlePasskeyLogin = async () => {
        setError('');
        setIsLoading(true);
        try {
            const { challenge_key, options } = await api.passkeyLoginOptions();
            const credential = await startAuthentication({ optionsJSON: options });
            await api.passkeyLoginVerify(credential, challenge_key);
            window.location.reload();
        } catch (err: any) {
            console.error('Passkey login error:', err);
            if (err?.name === 'NotAllowedError') {
                setError('Passkey sign-in was cancelled.');
            } else {
                setError('Passkey sign-in failed. Try your password instead.');
            }
        } finally {
            setIsLoading(false);
        }
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
        <div className="min-h-screen flex flex-col justify-center items-center p-4 relative overflow-hidden aurora-bg" style={{ background: 'var(--bg-main)' }}>
            {/* Aurora blobs */}
            <div className="absolute top-[-15%] left-[-8%] w-[55%] h-[55%] rounded-full pointer-events-none"
                style={{ background: 'radial-gradient(ellipse, rgba(0,210,255,0.18) 0%, transparent 70%)', filter: 'blur(60px)', animation: 'pulse 6s ease-in-out infinite' }} />
            <div className="absolute bottom-[-10%] right-[-8%] w-[50%] h-[50%] rounded-full pointer-events-none animation-delay-1000"
                style={{ background: 'radial-gradient(ellipse, rgba(127,0,255,0.15) 0%, transparent 70%)', filter: 'blur(80px)', animation: 'pulse 8s ease-in-out infinite' }} />
            <div className="absolute top-[40%] right-[15%] w-[30%] h-[30%] rounded-full pointer-events-none animation-delay-400"
                style={{ background: 'radial-gradient(ellipse, rgba(58,123,213,0.12) 0%, transparent 70%)', filter: 'blur(50px)', animation: 'pulse 7s ease-in-out infinite' }} />

            <div className="w-full max-w-md z-10 slide-up">
                {/* Header */}
                <div className="text-center mb-8">
                    <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl mb-4"
                        style={{ background: 'linear-gradient(135deg, rgba(0,210,255,0.2), rgba(127,0,255,0.2))', border: '1px solid rgba(0,210,255,0.3)', boxShadow: '0 0 24px rgba(0,210,255,0.2)' }}>
                        <BotIcon className="text-primary-400" size={36} />
                    </div>
                    <h1 className="text-4xl font-bold tracking-tight text-gradient">
                        Enterprise Omni-Agent
                    </h1>
                    <p className="text-sm text-slate-400 mt-2 font-medium tracking-wide uppercase">
                        Future-Ready AI Platform
                    </p>
                </div>

                {/* Login Card */}
                <div className="rounded-2xl p-8" style={{
                    background: 'rgba(12,12,32,0.75)',
                    backdropFilter: 'blur(20px) saturate(160%)',
                    WebkitBackdropFilter: 'blur(20px) saturate(160%)',
                    border: '1px solid rgba(255,255,255,0.08)',
                    boxShadow: '0 8px 40px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.06)',
                }}>
                    <h2 className="text-xl font-semibold text-white mb-6 tracking-tight">
                        Welcome back
                    </h2>

                    <form onSubmit={handleLogin} className="space-y-5">
                        {/* Email Field */}
                        <div>
                            <label htmlFor="email" className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                                Email Address
                            </label>
                            <div className="relative">
                                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
                                    <MailIcon size={16} className="text-slate-500" />
                                </div>
                                <input
                                    id="email"
                                    type="email"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    required
                                    className="block w-full pl-10 pr-4 py-3 rounded-xl text-sm text-white placeholder-slate-500 transition-all outline-none"
                                    style={{
                                        background: 'rgba(255,255,255,0.05)',
                                        border: '1px solid rgba(255,255,255,0.1)',
                                    }}
                                    onFocus={e => { e.currentTarget.style.border = '1px solid rgba(0,210,255,0.5)'; e.currentTarget.style.boxShadow = '0 0 0 3px rgba(0,210,255,0.12)'; }}
                                    onBlur={e => { e.currentTarget.style.border = '1px solid rgba(255,255,255,0.1)'; e.currentTarget.style.boxShadow = 'none'; }}
                                    placeholder="you@company.com"
                                    autoComplete="email"
                                />
                            </div>
                        </div>

                        {/* Password Field */}
                        <div>
                            <label htmlFor="password" className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                                Password
                            </label>
                            <div className="relative">
                                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
                                    <KeyIcon size={16} className="text-slate-500" />
                                </div>
                                <input
                                    id="password"
                                    type="password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    required
                                    className="block w-full pl-10 pr-4 py-3 rounded-xl text-sm text-white placeholder-slate-500 transition-all outline-none"
                                    style={{
                                        background: 'rgba(255,255,255,0.05)',
                                        border: '1px solid rgba(255,255,255,0.1)',
                                    }}
                                    onFocus={e => { e.currentTarget.style.border = '1px solid rgba(0,210,255,0.5)'; e.currentTarget.style.boxShadow = '0 0 0 3px rgba(0,210,255,0.12)'; }}
                                    onBlur={e => { e.currentTarget.style.border = '1px solid rgba(255,255,255,0.1)'; e.currentTarget.style.boxShadow = 'none'; }}
                                    placeholder="••••••••••••"
                                    autoComplete="current-password"
                                />
                            </div>
                        </div>

                        {/* Error Message */}
                        {error && (
                            <div className="flex items-start gap-2.5 p-3 rounded-xl" style={{ background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.25)' }}>
                                <span className="mt-0.5 text-red-400 flex-shrink-0">⚠</span>
                                <p className="text-sm text-red-300">{error}</p>
                            </div>
                        )}

                        {/* Login Button */}
                        <button
                            type="submit"
                            disabled={isLoading}
                            className="w-full py-3 px-4 text-white font-semibold rounded-xl transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                            style={{
                                background: 'linear-gradient(135deg, #00d2ff 0%, #3a7bd5 50%, #7f00ff 100%)',
                                boxShadow: isLoading ? 'none' : '0 4px 20px rgba(0,210,255,0.3)',
                            }}
                            onMouseEnter={e => { if (!isLoading) e.currentTarget.style.transform = 'translateY(-1px)'; }}
                            onMouseLeave={e => { e.currentTarget.style.transform = ''; }}
                            onMouseDown={e => { e.currentTarget.style.transform = 'translateY(1px)'; }}
                            onMouseUp={e => { e.currentTarget.style.transform = ''; }}
                        >
                            {isLoading ? (
                                <>
                                    <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                                    </svg>
                                    Signing in…
                                </>
                            ) : 'Sign In'}
                        </button>
                    </form>

                    {/* SSO Divider + Google button */}
                    {ssoEnabled && (
                        <>
                            <div className="mt-5 flex items-center gap-3">
                                <div className="flex-1 h-px" style={{ background: 'rgba(255,255,255,0.08)' }} />
                                <span className="text-xs text-slate-500 font-medium">or continue with</span>
                                <div className="flex-1 h-px" style={{ background: 'rgba(255,255,255,0.08)' }} />
                            </div>
                            <a
                                href="/api/sso/google/login"
                                className="mt-4 w-full flex items-center justify-center gap-3 py-3 px-4 rounded-xl text-slate-200 text-sm font-medium transition-all"
                                style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)' }}
                                onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.1)'; }}
                                onMouseLeave={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.06)'; }}
                            >
                                <svg className="w-4 h-4" viewBox="0 0 24 24">
                                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                                    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
                                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                                </svg>
                                Sign in with Google
                            </a>
                        </>
                    )}

                    {/* Passkey Sign-in */}
                    <button
                        type="button"
                        onClick={handlePasskeyLogin}
                        disabled={isLoading}
                        className="mt-4 w-full flex items-center justify-center gap-3 py-3 px-4 rounded-xl text-slate-200 text-sm font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                        style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)' }}
                        onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.1)'; }}
                        onMouseLeave={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.06)'; }}
                    >
                        <KeyIcon size={16} className="text-primary-400" />
                        Sign in with a passkey
                    </button>

                    {/* Divider */}
                    <div className="mt-6 flex items-center gap-3">
                        <div className="flex-1 h-px" style={{ background: 'rgba(255,255,255,0.08)' }} />
                        <span className="text-xs text-slate-500 font-medium">New here?</span>
                        <div className="flex-1 h-px" style={{ background: 'rgba(255,255,255,0.08)' }} />
                    </div>

                    {/* Signup Link */}
                    <button
                        onClick={() => setShowSignup(true)}
                        className="mt-4 w-full py-3 px-4 rounded-xl text-slate-300 text-sm font-medium transition-all"
                        style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)' }}
                        onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.08)'; e.currentTarget.style.color = '#fff'; }}
                        onMouseLeave={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.04)'; e.currentTarget.style.color = ''; }}
                    >
                        Create Account
                    </button>
                </div>

                {/* Demo Credentials */}
                <div className="mt-5 p-4 rounded-xl" style={{ background: 'rgba(0,210,255,0.06)', border: '1px solid rgba(0,210,255,0.15)' }}>
                    <p className="text-xs font-semibold text-primary-400 mb-2 uppercase tracking-wider">Demo Credentials</p>
                    <div className="space-y-1 text-xs text-slate-400">
                        <p>Super Admin: <span className="font-mono text-slate-300">super@omni.ai</span></p>
                        <p>Tenant Admin: <span className="font-mono text-slate-300">admin@acmecorp.com</span></p>
                        <p>Analyst: <span className="font-mono text-slate-300">analyst@acmecorp.com</span></p>
                    </div>
                </div>
            </div>
        </div>
    );
};
