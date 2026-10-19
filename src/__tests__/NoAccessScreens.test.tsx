/**
 * Phase 77 (D-05): a denied view renders the in-place no-access panel through ViewGate and
 * nothing of the forbidden screen mounts. Copy comes from 77-UI-SPEC.md "Copywriting Contract".
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { NoAccessPanel, ViewGate } from '../../components/NoAccessPanel';
import { ZeroAccessScreen } from '../../components/ZeroAccessScreen';
import type { RefreshResult } from '../../utils/permissionRefresh';
import { derivePermissionState } from '../../utils/permissions';
import type { User } from '../../types';

const mk = (role: string, permissions?: string[]): User =>
  ({ id: 'u1', name: 'U', email: 'u@x.test', role, tenantId: 't1', permissions }) as unknown as User;

function gate(user: User | null, view: string, render_: () => React.ReactNode, extra: Record<string, unknown> = {}) {
  const { hasPermission } = derivePermissionState(user);
  return (
    <ViewGate
      view={view as never}
      user={user}
      hasPermission={hasPermission}
      landing={'itam' as never}
      onGoToLanding={() => {}}
      render={render_}
      {...extra}
    />
  );
}

describe('ViewGate', () => {
  it('shows the skeleton and never calls render() while permissions are unknown', () => {
    const spy = vi.fn(() => <div>REAL SCREEN</div>);
    const { container } = render(gate(mk('Tenant Admin'), 'dashboard', spy));
    expect(spy).not.toHaveBeenCalled();
    expect(screen.queryByText(/You don't have access/)).toBeNull();
    expect(container.firstChild).not.toBeNull();
  });

  it('shows the panel and never calls render() for a denied view', () => {
    const spy = vi.fn(() => <div>REAL SCREEN</div>);
    render(gate(mk('itam_user', ['view:itam']), 'dashboard', spy));
    expect(spy).not.toHaveBeenCalled();
    expect(screen.getByRole('heading', { name: "You don't have access to Overview" })).toBeTruthy();
    expect(screen.queryByText('REAL SCREEN')).toBeNull();
  });

  it('renders the screen for an allowed view', () => {
    render(gate(mk('itam_user', ['view:itam']), 'itam', () => <div>REAL SCREEN</div>));
    expect(screen.getByText('REAL SCREEN')).toBeTruthy();
    expect(screen.queryByText(/You don't have access/)).toBeNull();
  });

  it('shows the unmapped variant for a view with no manifest entry, even for a super admin', () => {
    const spy = vi.fn(() => <div>REAL SCREEN</div>);
    render(gate(mk('Super Admin'), 'noSuchView', spy));
    expect(spy).not.toHaveBeenCalled();
    expect(screen.getByText("This screen isn't open to your role.")).toBeTruthy();
  });

  it('labels the Go to button with the landing screen and calls onGoToLanding', () => {
    const go = vi.fn();
    render(gate(mk('itam_user', ['view:itam']), 'dashboard', () => null, { onGoToLanding: go }));
    fireEvent.click(screen.getByRole('button', { name: 'Go to IT Asset Management' }));
    expect(go).toHaveBeenCalledTimes(1);
  });

  it('re-evaluates: access restored mounts the real screen without a click', () => {
    const denied = mk('itam_user', ['view:itam']);
    const { rerender } = render(gate(denied, 'dashboard', () => <div>REAL SCREEN</div>));
    expect(screen.queryByText('REAL SCREEN')).toBeNull();
    rerender(gate(mk('itam_user', ['view:itam', 'view:dashboard']), 'dashboard', () => <div>REAL SCREEN</div>));
    expect(screen.getByText('REAL SCREEN')).toBeTruthy();
  });
});

describe('NoAccessPanel variants', () => {
  it('role variant shows heading, body with the role name, and the required-permission chip', () => {
    render(
      <NoAccessPanel
        reason="role"
        screenLabel="Overview"
        permission={'view:dashboard' as never}
        roleName="itam_user"
        landingLabel="IT Asset Management"
        onGoToLanding={() => {}}
      />,
    );
    expect(screen.getByRole('heading', { name: "You don't have access to Overview" })).toBeTruthy();
    expect(
      screen.getByText(
        "Your role (itam_user) doesn't include the permission this screen needs. If you need access, ask your administrator.",
      ),
    ).toBeTruthy();
    expect(screen.getByText('Required permission')).toBeTruthy();
    expect(screen.getByText('view:dashboard')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Go to IT Asset Management' })).toBeTruthy();
  });

  it('switched_off variant names the screen and has no permission row', () => {
    render(<NoAccessPanel reason="switched_off" screenLabel="Compliance" landingLabel="Overview" onGoToLanding={() => {}} />);
    expect(screen.getByText('Compliance is switched off for your organization. Ask your administrator to turn it on.')).toBeTruthy();
    expect(screen.queryByText('Required permission')).toBeNull();
  });

  it('unmapped variant shows its copy and no permission row', () => {
    render(<NoAccessPanel reason="unmapped" screenLabel="ghost" />);
    expect(screen.getByText("This screen isn't open to your role.")).toBeTruthy();
    expect(screen.queryByText('Required permission')).toBeNull();
  });

  it('accessChanged shows the notice and the panel is not shown on first load without it', () => {
    const { rerender } = render(<NoAccessPanel reason="unmapped" screenLabel="x" />);
    expect(screen.queryByText('Your access was updated by an administrator.')).toBeNull();
    rerender(<NoAccessPanel reason="unmapped" screenLabel="x" accessChanged />);
    expect(screen.getByText('Your access was updated by an administrator.')).toBeTruthy();
  });

  it('moves focus to the heading on mount', () => {
    render(<NoAccessPanel reason="unmapped" screenLabel="x" />);
    expect(document.activeElement).toBe(screen.getByRole('heading', { name: "You don't have access to x" }));
  });

  it('renders no button when onGoToLanding or landingLabel is absent', () => {
    const { rerender } = render(<NoAccessPanel reason="unmapped" screenLabel="x" landingLabel="Overview" />);
    expect(screen.queryByRole('button')).toBeNull();
    rerender(<NoAccessPanel reason="unmapped" screenLabel="x" onGoToLanding={() => {}} />);
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('uses the single-card layout from the spec (w-full max-w-lg) and wraps long labels', () => {
    const { container } = render(<NoAccessPanel reason="unmapped" screenLabel={'A very long screen label '.repeat(8)} />);
    expect(container.querySelector('.max-w-lg.w-full')).not.toBeNull();
    expect(container.querySelector('h2')?.className).toMatch(/break-words/);
  });
});

describe('ZeroAccessScreen (D-07)', () => {
  const props = (over: Record<string, unknown> = {}) => ({
    email: 'long.address@example-company.test',
    roleName: 'Custom Role',
    tenantName: 'Acme Corp',
    onRetry: vi.fn(async (): Promise<RefreshResult> => 'same'),
    onSignOut: vi.fn(),
    ...over,
  });

  it('renders the title (focused), body, identity block with titled values, Retry and Sign out', () => {
    render(<ZeroAccessScreen {...props()} />);
    const h1 = screen.getByRole('heading', { level: 1, name: 'Your role has no screens yet' });
    expect(document.activeElement).toBe(h1);
    expect(screen.getByText('Ask your administrator to give your role access to at least one screen, then select Retry.')).toBeTruthy();
    for (const label of ['Signed in as', 'Role', 'Tenant']) expect(screen.getByText(label)).toBeTruthy();
    expect(screen.getByTitle('long.address@example-company.test')).toBeTruthy();
    expect(screen.getByTitle('Custom Role')).toBeTruthy();
    expect(screen.getByTitle('Acme Corp')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Retry permission check' })).toBeTruthy();
    expect(screen.getByRole('button', { name: /Sign out/ })).toBeTruthy();
    expect(screen.getByText('Omni-Agent')).toBeTruthy();
  });

  it('Retry calls onRetry once; while pending it is disabled, reads Checking... and ignores clicks', async () => {
    let resolve!: (v: RefreshResult) => void;
    const onRetry = vi.fn(() => new Promise<RefreshResult>(r => { resolve = r; }));
    render(<ZeroAccessScreen {...props({ onRetry })} />);
    const btn = screen.getByRole('button', { name: 'Retry permission check' }) as HTMLButtonElement;
    fireEvent.click(btn);
    fireEvent.click(btn);
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(btn.disabled).toBe(true);
    expect(btn.textContent).toContain('Checking...');
    await act(async () => { resolve('same'); });
    expect(btn.disabled).toBe(false);
  });

  it("'same' shows the still-no-screens line with the last-checked time", async () => {
    render(<ZeroAccessScreen {...props()} />);
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Retry permission check' })); });
    expect(screen.getByText(/^Still no screens for your role\. Last checked .+\.$/)).toBeTruthy();
  });

  it("'error' shows the red role=alert message and keeps Sign out enabled", async () => {
    const onRetry = vi.fn(async (): Promise<RefreshResult> => 'error');
    render(<ZeroAccessScreen {...props({ onRetry })} />);
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Retry permission check' })); });
    const alert = screen.getByRole('alert');
    expect(alert.textContent).toBe("Couldn't check your permissions. Check your connection and try again.");
    expect((screen.getByRole('button', { name: /Sign out/ }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('Sign out is enabled and works while Retry is pending forever', () => {
    const onSignOut = vi.fn();
    render(<ZeroAccessScreen {...props({ onRetry: vi.fn(() => new Promise<RefreshResult>(() => {})), onSignOut })} />);
    fireEvent.click(screen.getByRole('button', { name: 'Retry permission check' }));
    const out = screen.getByRole('button', { name: /Sign out/ }) as HTMLButtonElement;
    expect(out.disabled).toBe(false);
    fireEvent.click(out);
    expect(onSignOut).toHaveBeenCalledTimes(1);
  });

  it('uses the company name when branding provides one', () => {
    render(<ZeroAccessScreen {...props({ companyName: 'Contoso' })} />);
    expect(screen.getByText('Contoso')).toBeTruthy();
  });
});
