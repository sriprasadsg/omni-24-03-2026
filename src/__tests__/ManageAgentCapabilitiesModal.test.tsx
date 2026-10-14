/**
 * The per-agent capability screen lists only what the agent's tenant may use
 * (agent.allowedCapabilities, set from the Super Admin's choice in Manage Tenant).
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { Agent } from '../../types';
import { ManageAgentCapabilitiesModal } from '../../components/ManageAgentCapabilitiesModal';

const agent = {
  id: 'a1', hostname: 'pc1', capabilities: ['fim', 'pii_scanner'],
  availableCapabilities: ['fim', 'pii_scanner', 'remote_access'],
} as unknown as Agent;

describe('ManageAgentCapabilitiesModal', () => {
  it('hides capabilities the tenant lacks and never saves one', () => {
    const onSave = vi.fn();
    render(<ManageAgentCapabilitiesModal isOpen onClose={() => {}} onSave={onSave}
      agent={{ ...agent, allowedCapabilities: ['fim', 'remote_access', 'agent_update'] } as Agent} />);
    expect(screen.getByText('File Integrity Monitoring')).toBeTruthy();
    expect(screen.getByText('Remote Access')).toBeTruthy();
    expect(screen.queryByText('PII Data Scanner')).toBeNull();
    expect(screen.queryByText('Data & Privacy')).toBeNull();   // a group with nothing left goes too
    fireEvent.click(screen.getByText('Save Capabilities'));
    expect(onSave.mock.calls[0][0].capabilities).toEqual(['fim']);
  });

  it('lists everything for an agent record without the list', () => {
    render(<ManageAgentCapabilitiesModal isOpen onClose={() => {}} onSave={() => {}} agent={agent} />);
    expect(screen.getByText('PII Data Scanner')).toBeTruthy();
  });
});
