import React, { useEffect, useRef, useState } from 'react';
import { fetchInviteStatus, type InviteStatus } from '../services/partnerApi';
import { BotIcon, ClockIcon } from './icons';

/**
 * Phase 87 (PART-02, D-09, D-17, D-20; 87-UI-SPEC section 3): the public Accept invite page. It sits outside the
 * signed-in shell (no sidebar, no header, no organization data). On load the token is read once, kept in
 * component memory and removed from the address bar before any request is made, so it is not left in history
 * or a referrer. The organization name and email come from the server and are rendered as React text only.
 */

type View = 'checking' | 'form' | 'expired' | 'used' | 'invalid' | 'network';

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

const AcceptInvitePage: React.FC = () => {
  const tokenRef = useRef<string | null | undefined>(undefined);
  const startedRef = useRef(false);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [view, setView] = useState<View>('checking');
  const [status, setStatus] = useState<InviteStatus | null>(null);

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
