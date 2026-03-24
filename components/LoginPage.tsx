import React, { useState } from 'react';
import { useUser } from '../contexts/UserContext';
import { BotIcon, MailIcon, KeyIcon } from './icons';
import { User } from '../types';
import { SignupForm } from './SignupForm';

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
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);

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
            // Call Real API
            const data = await api.login(email, password);

            // Store Token
            localStorage.setItem('token', data.access_token);

            // Notify Context/App (Mocking the user object return for now so App state updates)
            // Ideally we fetch /me here

            // If onLogin is passed (from App.tsx), call it with success mock
            if (onLogin) {
                await onLogin(email, password); // This will update App state
            } else {
                // Fallback
                window.location.reload();
            }

        } catch (err) {
            console.error('Login error:', err);
            setError('Invalid email or password.');
        } finally {
            setIsLoading(false);
        }
    };

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
