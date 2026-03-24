import React, { useState } from 'react';
import { useUser } from '../contexts/UserContext';
import { BotIcon, CogIcon } from '../components/icons';

const FormWrapper: React.FC<{ children: React.ReactNode; title: string }> = ({ children, title }) => (
    <div className="w-full max-w-md">
        <div className="bg-white dark:bg-gray-800 shadow-2xl rounded-xl p-8">
            <div className="text-center mb-8">
                <BotIcon className="text-primary-500 mx-auto" size={48} />
                <h1 className="text-2xl font-bold mt-4 text-gray-800 dark:text-white">{title}</h1>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">to the Omni-Agent AI Platform</p>
            </div>
            {children}
        </div>
    </div>
);


const LoginForm: React.FC<{ onSwitch: () => void }> = ({ onSwitch }) => {
    const { login } = useUser();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsLoading(true);
        setError(null);
        const success = await login(email, password);
        if (!success) {
            setError('Invalid email or password. Please try again.');
            setIsLoading(false);
        }
    };

    return (
        <form onSubmit={handleSubmit} className="space-y-6">
            {error && (
                <div className="bg-red-100 dark:bg-red-900/50 border border-red-400 dark:border-red-600 text-red-700 dark:text-red-200 px-4 py-3 rounded-lg relative text-sm">
                    {error}
                </div>
            )}
            <div>
                <label htmlFor="email" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Email address</label>
                <input
                    id="email"
                    name="email"
                    type="email"
                    autoComplete="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                />
            </div>
            <div>
                <label htmlFor="password" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Password</label>
                <input
                    id="password"
                    name="password"
                    type="password"
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                />
            </div>
            <div>
                <button
                    type="submit"
                    disabled={isLoading}
                    className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:bg-primary-400"
                >
                    {isLoading ? <CogIcon className="animate-spin" /> : 'Sign in'}
                </button>
            </div>
            <p className="text-center text-sm">
                <a href="#" onClick={(e) => { e.preventDefault(); onSwitch(); }} className="font-medium text-primary-600 hover:text-primary-500 dark:text-primary-400">
                    Don't have an account? Sign up
                </a>
            </p>
        </form>
    );
};

const SignupForm: React.FC<{ onSwitch: () => void }> = ({ onSwitch }) => {
    const { registerTenant } = useUser();
    const [companyName, setCompanyName] = useState('');
    const [name, setName] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsLoading(true);
        setError(null);
        const success = await registerTenant({ companyName, name, email, password });
        if (!success) {
            setError('Failed to register. The company name or email might already be in use.');
            setIsLoading(false);
        }
    };

    return (
        <form onSubmit={handleSubmit} className="space-y-4">
             {error && (
                <div className="bg-red-100 dark:bg-red-900/50 border border-red-400 dark:border-red-600 text-red-700 dark:text-red-200 px-4 py-3 rounded-lg relative text-sm">
                    {error}
                </div>
            )}
            <div>
                <label htmlFor="companyName" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Company Name</label>
                <input id="companyName" type="text" required value={companyName} onChange={(e) => setCompanyName(e.target.value)} className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm"/>
            </div>
            <div>
                <label htmlFor="name" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Your Name</label>
                <input id="name" type="text" required value={name} onChange={(e) => setName(e.target.value)} className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm"/>
            </div>
            <div>
                <label htmlFor="signup-email" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Email address</label>
                <input id="signup-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm"/>
            </div>
            <div>
                <label htmlFor="signup-password" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Password</label>
                <input id="signup-password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm"/>
            </div>
             <div>
                <button
                    type="submit"
                    disabled={isLoading}
                    className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:bg-primary-400"
                >
                    {isLoading ? <CogIcon className="animate-spin" /> : 'Create Account'}
                </button>
            </div>
            <p className="text-center text-sm">
                <a href="#" onClick={(e) => { e.preventDefault(); onSwitch(); }} className="font-medium text-primary-600 hover:text-primary-500 dark:text-primary-400">
                    Already have an account? Sign in
                </a>
            </p>
        </form>
    );
};


export const LoginPage: React.FC = () => {
    const [isRegistering, setIsRegistering] = useState(false);

    return (
        <div className="min-h-screen bg-gray-100 dark:bg-gray-900 flex flex-col justify-center items-center p-4">
            <FormWrapper title={isRegistering ? 'Create Workspace' : 'Sign in'}>
                {isRegistering ? (
                    <SignupForm onSwitch={() => setIsRegistering(false)} />
                ) : (
                    <LoginForm onSwitch={() => setIsRegistering(true)} />
                )}
            </FormWrapper>
            <div className="text-center mt-8 text-xs text-gray-400 dark:text-gray-500 max-w-md">
                <p>For demonstration, you can also log in with predefined user accounts: `super@omni.ai`, `alice@acme.com`, `bob@acme.com`, or `eve@initech.com`. The password for all accounts is `password123`.</p>
            </div>
        </div>
    );
};