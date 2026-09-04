import { describe, it, expect, vi } from 'vitest';
import { resolveKeyEventToFrame, normalizeCanvasPoint } from '../types';
import { disconnectRemoteSession, getRemoteCapabilities } from '../services/apiService';
import type { FleetGeoAgent } from '../../services/apiService';

// Mock agent data for testing
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
  describe('DOM_CODE_TO_VK mapping', () => {
    it('maps extended keys to correct virtual key codes', () => {
      expect(resolveKeyEventToFrame({ key: 'ArrowUp', extended: true })).toEqual({ vk: 38, extended: true });
      expect(resolveKeyEventToFrame({ key: 'ArrowDown', extended: true })).toEqual({ vk: 40, extended: true });
      expect(resolveKeyEventToFrame({ key: 'Insert', extended: true })).toEqual({ vk: 39, extended: true });
      expect(resolveKeyEventToFrame({ key: 'Delete', extended: true })).toEqual({ vk: 46, extended: true });
    });

    it('maps printable characters to UTF-16 code unit with vk=0', () => {
      expect(resolveKeyEventToFrame({ key: 'a', extended: false })).toEqual({ vk: 0, unicode: 97 });
      expect(resolveKeyEventToFrame({ key: 'A', extended: false })).toEqual({ vk: 0, unicode: 65 });
      expect(resolveKeyEventToFrame({ key: ' ', extended: false })).toEqual({ vk: 0, unicode: 32 });
    });

    it('handles unmapped characters by returning undefined', () => {
      expect(resolveKeyEventToFrame({ key: '!@#$%^&*()', extended: false })).toBeUndefined();
    });
  });

  describe('normalizeCanvasPoint', () => {
    it('clamps coordinates to 0..1 inclusive', () => {
      expect(normalizeCanvasPoint(-10, 5, 100, 100)).toEqual([0, 0]);
      expect(normalizeCanvasPoint(150, 150, 100, 100)).toEqual([1, 1]);
      expect(normalizeCanvasPoint(50, 50, 100, 100)).toEqual([0.5, 0.5]);
    });

    it('handles zero division safely', () => {
      expect(normalizeCanvasPoint(0, 0, 0, 0)).toEqual([0, 0]);
    });
  });

  describe('key resolution', () => {
    it('handles extended keys correctly', () => {
      const result = resolveKeyEventToFrame({ key: 'Control', extended: true });
      expect(result.vk).toBeGreaterThan(0);
      expect(result.extended).toBe(true);
    });

    it('handles single-character printable keys', () => {
      expect(resolveKeyEventToFrame({ key: 'a', extended: false })).toHaveProperty('unicode', 97);
      expect(resolveKeyEventToFrame({ key: 'Enter', extended: false })).toEqual({ vk: 13, extended: false });
    });
  });

  describe('API functions', () => {
    it('disconnectRemoteSession returns success response on success', async () => {
      // Mock the API response
      const mockResponse = { success: true, data: { session_id: 'test-session' } };
      vi.spyOn(global, 'authFetch').mockResolvedValueOnce(mockResponse);

      const result = await disconnectRemoteSession('test-session');
      expect(result).toEqual({ success: true, data: { session_id: 'test-session' } });
    });

    it('disconnectRemoteSession handles errors gracefully', async () => {
      const mockError = new Error('Network error');
      vi.spyOn(global, 'authFetch').mockRejectedValueOnce(mockError);

      const result = await disconnectRemoteSession('test-session');
      expect(result).toEqual({ error: mockError });
    });

    it('getRemoteCapabilities returns capabilities on success', async () => {
      const mockResponse = { can_view: true, can_control: false };
      vi.spyOn(global, 'authFetch').mockResolvedValueOnce(mockResponse);

      const result = await getRemoteCapabilities();
      expect(result).toEqual({ can_view: true, can_control: false });
    });

    it('getRemoteCapabilities handles errors gracefully', async () => {
      const mockError = new Error('API failure');
      vi.spyOn(global, 'authFetch').mockRejectedValueOnce(mockError);

      const result = await getRemoteCapabilities();
      expect(result).toEqual({ error: mockError, can_view: false, can_control: false });
    });
  });
});