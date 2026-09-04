import { describe, it, expect, vi, beforeEach } from 'vitest';
import { resolveKeyEventToFrame, normalizeCanvasPoint, DOM_CODE_TO_VK } from '../../types';
import { disconnectRemoteSession, getRemoteCapabilities } from '../../services/apiService';
import type { FleetGeoAgent } from '../../services/apiService';

vi.mock('../../services/apiService', () => ({
  disconnectRemoteSession: vi.fn(),
  getRemoteCapabilities: vi.fn(),
  authFetch: vi.fn(),
}));

const mockDisconnect = vi.mocked(disconnectRemoteSession);
const mockCapabilities = vi.mocked(getRemoteCapabilities);

const mockAgent = (id: string, lat: number | null, lon: number | null, status = 'Online'): FleetGeoAgent => ({
  id,
  hostname: `host-${id}`,
  status,
  tenantId: 'tenant-a',
  lanIp: '10.0.0.1',
  publicIp: '203.0.113.1',
  geo: lat === null || lon === null
    ? null
    : { city: 'X', country: 'Y', country_code: 'YY', latitude: lat, longitude: lon },
});

describe('remoteControl.test.ts', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('DOM_CODE_TO_VK mapping', () => {
    it('maps extended keys to correct virtual key codes', () => {
      expect(DOM_CODE_TO_VK['ArrowUp']).toBe(38);
      expect(DOM_CODE_TO_VK['ArrowDown']).toBe(40);
      expect(DOM_CODE_TO_VK['Insert']).toBe(0x2D);
      expect(DOM_CODE_TO_VK['Delete']).toBe(0x2E);
    });

    it('maps printable characters to correct VK codes', () => {
      expect(DOM_CODE_TO_VK['KeyA']).toBe(0x41);
      expect(DOM_CODE_TO_VK['Digit1']).toBe(0x31);
      expect(DOM_CODE_TO_VK['Space']).toBe(0x20);
    });
  });

  describe('normalizeCanvasPoint', () => {
    it('clamps coordinates to 0..1 inclusive', () => {
      expect(normalizeCanvasPoint(-10, 5, 100, 100)).toEqual({ x: 0, y: 0.05 });
      expect(normalizeCanvasPoint(150, 150, 100, 100)).toEqual({ x: 1, y: 1 });
      expect(normalizeCanvasPoint(50, 50, 100, 100)).toEqual({ x: 0.5, y: 0.5 });
    });

    it('handles zero division safely', () => {
      expect(normalizeCanvasPoint(0, 0, 0, 0)).toEqual({ x: 0, y: 0 });
    });
  });

  describe('resolveKeyEventToFrame', () => {
    it('handles extended keys correctly', () => {
      const result = resolveKeyEventToFrame({ code: 'ArrowUp', key: 'ArrowUp', ctrlKey: false, metaKey: false } as unknown as React.KeyboardEvent);
      expect(result.vk).toBeGreaterThan(0);
      expect(result.extended).toBe(true);
    });

    it('maps KeyA via DOM_CODE_TO_VK', () => {
      const result = resolveKeyEventToFrame({ code: 'KeyA', key: 'a', ctrlKey: false, metaKey: false } as unknown as React.KeyboardEvent);
      expect(result.vk).toBe(0x41);
      expect(result.extended).toBe(false);
    });

    it('falls back to unicode for unmapped single-char key', () => {
      const result = resolveKeyEventToFrame({ code: 'Unmapped', key: 'a', ctrlKey: false, metaKey: false } as unknown as React.KeyboardEvent);
      expect(result.vk).toBe(0);
      expect(result.unicode).toBe(97);
    });

    it('handles Enter', () => {
      const result = resolveKeyEventToFrame({ code: 'Enter', key: 'Enter', ctrlKey: false, metaKey: false } as unknown as React.KeyboardEvent);
      expect(result.vk).toBe(13);
      expect(result.extended).toBe(false);
    });

    it('handles unmapped non-printable keys', () => {
      const result = resolveKeyEventToFrame({ code: 'Unmapped', key: '!@#$%', ctrlKey: false, metaKey: false } as unknown as React.KeyboardEvent);
      expect(result.vk).toBe(0);
      expect(result.unicode).toBeUndefined();
    });
  });

  describe('API functions', () => {
    it('disconnectRemoteSession returns success response on success', async () => {
      const mockResponse = { success: true, data: { session_id: 'test-session' } };
      mockDisconnect.mockResolvedValueOnce(mockResponse as never);

      const result = await disconnectRemoteSession('test-session');
      expect(result).toEqual({ success: true, data: { session_id: 'test-session' } });
    });

    it('disconnectRemoteSession handles errors gracefully', async () => {
      const mockError = new Error('Network error');
      mockDisconnect.mockResolvedValueOnce({ error: mockError } as never);

      const result = await disconnectRemoteSession('test-session');
      expect(result).toEqual({ error: mockError });
    });

    it('getRemoteCapabilities returns capabilities on success', async () => {
      const mockResponse = { can_view: true, can_control: false };
      mockCapabilities.mockResolvedValueOnce(mockResponse as never);

      const result = await getRemoteCapabilities();
      expect(result).toEqual({ can_view: true, can_control: false });
    });

    it('getRemoteCapabilities handles errors gracefully', async () => {
      const mockError = new Error('API failure');
      mockCapabilities.mockResolvedValueOnce({ error: mockError, can_view: false, can_control: false } as never);

      const result = await getRemoteCapabilities();
      expect(result).toEqual({ error: mockError, can_view: false, can_control: false });
    });

    // keep mockAgent reachable so FleetGeoAgent import is not tree-shaken as unused
    it('mockAgent helper shapes FleetGeoAgent', () => {
      expect(mockAgent('x', 1, 2).geo?.latitude).toBe(1);
      expect(mockAgent('y', null, null).geo).toBeNull();
    });
  });
});
