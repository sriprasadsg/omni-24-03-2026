/**
 * Phase 77 (D-05): a denied view renders the in-place no-access panel through ViewGate and
 * nothing of the forbidden screen mounts. Copy comes from 77-UI-SPEC.md "Copywriting Contract".
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { NoAccessPanel, ViewGate } from '../../components/NoAccessPanel';
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
