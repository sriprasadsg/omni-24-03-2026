import React, { useEffect, useId, useRef, useState } from 'react';
import { PartnerApiError, acceptInvite, fetchInviteStatus, type InviteStatus } from '../services/partnerApi';
import { login } from '../services/apiService';
import { BotIcon, CheckIcon, ClockIcon, EyeIcon, EyeOffIcon, XIcon } from './icons';

/**
 * Phase 87 (PART-02, D-09, D-17, D-20; 87-UI-SPEC section 3): the public Accept invite page. It sits outside the
 * signed-in shell (no sidebar, no header, no organization data). On load the token is read once, kept in
 * component memory and removed from the address bar before any request is made, so it is not left in history
 * or a referrer. The organization name and email come from the server and are rendered as React text only.
 *
 * Once the password is set the page signs the person in once (the existing login call, which stores only the
 * session token) and loads the app shell. It builds no MFA UI: an administrator role meets the existing required
 * two-step set-up there (D-20). The password is never logged, never put in a URL and never kept after the call.
 */

type View = 'checking' | 'form' | 'signing_in' | 'done' | 'expired' | 'used' | 'invalid' | 'network';

// Mirrors backend auth_utils.validate_password_complexity (and the rules list of ResetPasswordModal).
const RULES: { label: string; test: (pw: string) => boolean }[] = [
  { label: 'At least 8 characters', test: pw => pw.length >= 8 },
  { label: 'An uppercase letter', test: pw => /[A-Z]/.test(pw) },
  { label: 'A lowercase letter', test: pw => /[a-z]/.test(pw) },
  { label: 'A digit', test: pw => /\d/.test(pw) },
  { label: 'A special character', test: pw => /[^A-Za-z0-9]/.test(pw) },
];

const INPUT =
  'w-full min-h-10 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 pl-3 pr-11 py-2 text-sm text-gray-900 dark:text-white disabled:opacity-60';
const LABEL = 'block text-sm font-semibold text-gray-900 dark:text-white mb-1';
const FIELD_ERROR = 'text-xs text-red-600 dark:text-red-400';
const TOGGLE =
  'absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-r-md text-gray-500 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white';

const NETWORK_ERROR = "Couldn't reach the platform. Check your connection and try again.";

const PRIMARY_LINK =
  'inline-flex w-full items-center justify-center gap-2 min-h-10 rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white hover:bg-primary-700';
const SECONDARY_LINK =
  'inline-flex w-full items-center justify-center gap-2 min-h-10 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 ' +
  'px-4 py-2 text-sm font-semibold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700';
const BODY = 'text-sm text-gray-600 dark:text-gray-300';

/** Anything the page cannot classify is Invalid, never an empty form. */
function classify(status: InviteStatus | null | undefined): View {
  switch (status?.state) {
    case 'valid': return 'form';
    case 'expired': return 'expired';
    case 'used': return 'used';
    default: return 'invalid';
  }
}

const SignInLink: React.FC<{ accent: boolean }> = ({ accent }) => (
  <a href="/login" className={accent ? PRIMARY_LINK : SECONDARY_LINK}>Go to sign in</a>
);

interface PasswordFieldProps {
  id: string;
  label: string;
  value: string;
  visible: boolean;
  disabled: boolean;
  autoComplete: string;
  describedBy?: string;
  onChange: (value: string) => void;
  onToggle: () => void;
}

const PasswordField: React.FC<PasswordFieldProps> = ({ id, label, value, visible, disabled, autoComplete, describedBy, onChange, onToggle }) => (
  <div>
    <label htmlFor={id} className={LABEL}>{label}</label>
    <div className="relative">
      <input
        id={id}
        type={visible ? 'text' : 'password'}
        autoComplete={autoComplete}
        aria-required="true"
        aria-describedby={describedBy}
        value={value}
        disabled={disabled}
        onChange={e => onChange(e.target.value)}
        className={INPUT}
      />
      <button
        type="button"
        onClick={onToggle}
        aria-label={visible ? 'Hide password' : 'Show password'}
        aria-pressed={visible}
        className={TOGGLE}
      >
        {visible ? <EyeOffIcon size={16} aria-hidden="true" /> : <EyeIcon size={16} aria-hidden="true" />}
      </button>
    </div>
  </div>
);

const AcceptInvitePage: React.FC = () => {
  const tokenRef = useRef<string | null | undefined>(undefined);
  const startedRef = useRef(false);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [view, setView] = useState<View>('checking');
  const [status, setStatus] = useState<InviteStatus | null>(null);
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [touched, setTouched] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [pending, setPending] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const pendingRef = useRef(false);
  const ids = useId();

  const checkInvite = (token: string) => {
    setView('checking');
    fetchInviteStatus(token).then(
      result => {
        setStatus(result);
        setView(classify(result));
      },
      () => setView('network'),
    );
  };

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    if (tokenRef.current === undefined) {
      tokenRef.current = new URLSearchParams(window.location.search).get('token')?.trim() || null;
      // The token lives in memory from here on; the address bar no longer carries it.
      window.history.replaceState({}, '', '/accept-invite');
    }
    const token = tokenRef.current;
    if (!token) {
      setView('invalid');
      return;
    }
    checkInvite(token);
  }, []);

  useEffect(() => {
    headingRef.current?.focus();
  }, [view]);

  const rulesMet = RULES.map(rule => rule.test(password));
  const allRulesMet = rulesMet.every(Boolean);
  const mismatch = confirm.length > 0 && confirm !== password;
  const canSubmit = allRulesMet && password === confirm && !pending;

  const leaveForm = (next: View, nextStatus?: InviteStatus) => {
    setPassword('');
    setConfirm('');
    if (nextStatus) setStatus(nextStatus);
    setView(next);
  };

  /** A 400 may mean the link just expired or was used: ask again, else show the server's words verbatim. */
  const explainRefusal = async (error: PartnerApiError, token: string) => {
    try {
      const fresh = await fetchInviteStatus(token);
      const next = classify(fresh);
      if (next !== 'form') {
        leaveForm(next, fresh);
        return;
      }
    } catch {
      // Could not ask again: the refusal below is still the truthful answer.
    }
    setFormError(error.message);
  };

  const signInOnce = async () => {
    const address = status?.email?.trim();
    let signedIn = false;
    try {
      if (address) {
        const data = await login(address, password);
        signedIn = Boolean(data?.access_token);
      }
    } catch {
      signedIn = false;
    }
    setPassword('');
    setConfirm('');
    if (signedIn) window.location.replace('/');
    else setView('done');
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const token = tokenRef.current;
    if (!token || !canSubmit || pendingRef.current) return;
    pendingRef.current = true;
    setPending(true);
    setFormError(null);
    try {
      await acceptInvite(token, password);
    } catch (e) {
      if (e instanceof PartnerApiError) {
        if (e.status === 400) await explainRefusal(e, token);
        else setFormError(`Couldn't set your password: ${e.message.replace(/\.+$/, '')}. Try again.`);
      } else {
        setFormError("Couldn't set your password. Check your connection and try again.");
      }
      pendingRef.current = false;
      setPending(false);
      return;
    }
    pendingRef.current = false;
    setPending(false);
    setView('signing_in');
    await signInOnce();
  };

  const organizationName = status?.organizationName?.trim() || 'your organization';
  const email = status?.email?.trim();

  const heading = (text: string) => (
    <h1 ref={headingRef} tabIndex={-1} className="text-lg font-semibold text-gray-900 dark:text-white break-words focus:outline-none">
      {text}
    </h1>
  );

  let body: React.ReactNode;
  switch (view) {
    case 'checking':
      body = (
        <div aria-busy="true" className="space-y-4">
          {heading('Checking your invite...')}
          <div className="h-4 w-48 max-w-full animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
        </div>
      );
      break;
    case 'form':
      body = (
        <div className="space-y-4">
          {heading('Set your password')}
          <p className={`${BODY} break-words`}>
            {`Welcome to ${organizationName}. Choose a password to finish setting up your account.`}
          </p>
          {email && (
            <div>
              <p className="text-sm font-semibold text-gray-900 dark:text-white">Email address</p>
              <p className="text-sm text-gray-600 dark:text-gray-300 break-all">{email}</p>
            </div>
          )}
          <form onSubmit={handleSubmit} noValidate className="space-y-4">
            <PasswordField
              id={`${ids}-new`}
              label="New password"
              value={password}
              visible={showPassword}
              disabled={pending}
              autoComplete="new-password"
              describedBy={`${ids}-rules`}
              onChange={value => { setPassword(value); setTouched(true); }}
              onToggle={() => setShowPassword(v => !v)}
            />
            <ul
              id={`${ids}-rules`}
              aria-label="Password rules"
              aria-live={touched ? 'polite' : undefined}
              className="space-y-1"
            >
              {RULES.map((rule, i) => (
                <li
                  key={rule.label}
                  data-met={String(rulesMet[i])}
                  className={`flex items-center gap-2 text-xs ${rulesMet[i] ? 'text-green-700 dark:text-green-400' : 'text-gray-500 dark:text-gray-400'}`}
                >
                  {rulesMet[i]
                    ? <CheckIcon size={14} role="img" aria-label="Met" />
                    : <XIcon size={14} role="img" aria-label="Not met" />}
                  {rule.label}
                </li>
              ))}
            </ul>
            <PasswordField
              id={`${ids}-confirm`}
              label="Confirm password"
              value={confirm}
              visible={showConfirm}
              disabled={pending}
              autoComplete="new-password"
              describedBy={mismatch ? `${ids}-mismatch` : undefined}
              onChange={setConfirm}
              onToggle={() => setShowConfirm(v => !v)}
            />
            {mismatch && <p id={`${ids}-mismatch`} className={FIELD_ERROR}>The passwords don't match.</p>}
            {formError && (
              <div
                role="alert"
                className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-400/25 dark:bg-red-400/10 dark:text-red-300 break-words"
              >
                {formError}
              </div>
            )}
            <button
              type="submit"
              disabled={!canSubmit}
              className="inline-flex w-full items-center justify-center gap-2 min-h-10 rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white hover:bg-primary-700 disabled:opacity-60"
            >
              {pending ? 'Setting password...' : 'Set password'}
            </button>
          </form>
        </div>
      );
      break;
    case 'signing_in':
      body = (
        <div className="space-y-4">
          {heading('Password set')}
          <div role="status" className={`flex items-center gap-2 ${BODY}`}>
            <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Signing you in...
          </div>
        </div>
      );
      break;
    case 'done':
      body = (
        <div className="space-y-4">
          {heading('Password set')}
          <p className={BODY}>Your password is set. Sign in to continue.</p>
          <SignInLink accent />
        </div>
      );
      break;
    case 'expired':
      body = (
        <div className="space-y-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-300">
            <ClockIcon size={24} aria-hidden="true" />
          </div>
          {heading('This invite has expired')}
          <p className={BODY}>Invite links work for 7 days. Ask the person who invited you to send a new one.</p>
          <SignInLink accent={false} />
        </div>
      );
      break;
    case 'used':
      body = (
        <div className="space-y-4">
          {heading('This invite was already used')}
          <p className={BODY}>
            If you have set your password, sign in below. If you did not, ask the person who invited you to send a new link.
          </p>
          <SignInLink accent />
        </div>
      );
      break;
    case 'network':
      body = (
        <div className="space-y-4">
          {heading('Set your password')}
          <div
            role="alert"
            className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-400/25 dark:bg-red-400/10 dark:text-red-300"
          >
            {NETWORK_ERROR}
          </div>
          <button type="button" className={SECONDARY_LINK} onClick={() => tokenRef.current && checkInvite(tokenRef.current)}>
            Try again
          </button>
        </div>
      );
      break;
    default:
      body = (
        <div className="space-y-4">
          {heading("This invite link isn't valid")}
          <p className={BODY}>
            Check that you opened the whole link from your email, or ask the person who invited you to send a new one.
          </p>
          <SignInLink accent={false} />
        </div>
      );
  }

  return (
    <div className="dark min-h-screen flex flex-col items-center p-4 pt-12 md:justify-center md:pt-4 relative overflow-hidden aurora-bg" style={{ background: 'var(--bg-main)' }}>
      <div className="w-full max-w-md z-10">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl mb-4 bg-primary-500/10 border border-primary-400/30">
            <BotIcon className="text-primary-400" size={36} aria-hidden="true" />
          </div>
          <p className="text-2xl font-semibold tracking-tight text-white">Enterprise Omni-Agent</p>
        </div>
        <div className="card max-w-md mx-auto p-8">{body}</div>
      </div>
    </div>
  );
};

export default AcceptInvitePage;
