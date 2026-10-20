/**
 * Agent > Patching > System Information showed "Unknown" for every field on
 * Windows: the Rust agent sends flat bios_* / last_boot fields while the tab
 * read only the Python agent's nested bios_info / uptime.
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AgentPatchingTab } from '../../components/AgentPatchingTab';
import type { Agent } from '../../types';

const agentWith = (system_patching: Record<string, unknown>) =>
  ({ id: 'agent-1', hostname: 'host', meta: { system_patching } } as unknown as Agent);

describe('AgentPatchingTab', () => {
  it('shows the Windows (Rust) agent fields', () => {
    render(<AgentPatchingTab agent={agentWith({
      bios_version: 'X72 Ver. 01.05.04', bios_manufacturer: 'HP', bios_release_date: '05/14/2025',
      last_boot: '2026-10-12T07:15:12Z', uptime_seconds: 14548, pending_updates: [],
    })} />);
    expect(screen.getByText('X72 Ver. 01.05.04')).toBeTruthy();
    expect(screen.getByText('HP')).toBeTruthy();
    expect(screen.getByText('05/14/2025')).toBeTruthy();
    expect(screen.getByText(new Date('2026-10-12T07:15:12Z').toLocaleString())).toBeTruthy();
    expect(screen.queryByText('Unknown')).toBeNull();
  });

  it('shows the Linux (Python) agent fields and treats "Unknown" as missing', () => {
    render(<AgentPatchingTab agent={agentWith({
      bios_info: { version: 'Hyper-V UEFI Release v4.1', manufacturer: 'Unknown', release_date: '04/22/2026' },
      uptime: { boot_time: '2026-10-12T09:03:09+00:00', uptime_seconds: 100 }, pending_updates: [],
    })} />);
    expect(screen.getByText('Hyper-V UEFI Release v4.1')).toBeTruthy();
    expect(screen.getByText('04/22/2026')).toBeTruthy();
    expect(screen.getAllByText('Unknown')).toHaveLength(1);
  });
});
