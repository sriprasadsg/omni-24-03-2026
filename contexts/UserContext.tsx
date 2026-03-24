import React, { createContext, useContext } from 'react';
import { User, Permission, NewUserPayload, NewTenantPayload } from '../types';

export interface UserContextType {
  currentUser: User | null;
  login: (email: string, password: string) => Promise<boolean>;
  logout: () => void;
  signup: (payload: { companyName: string; name: string; email: string; password: string }) => Promise<boolean>;
  registerTenant: (payload: NewTenantPayload) => Promise<boolean>;
  hasPermission: (permission: Permission) => boolean;
  enabledFeatures: Permission[];
}

const defaultContext: UserContextType = {
  currentUser: null,
  login: async () => false,
  logout: () => { },
  signup: async () => false,
  registerTenant: async () => false,
  hasPermission: () => false,
  enabledFeatures: [],
};

console.log('[UserContext] Module initialized');

export const UserContext = createContext<UserContextType>(defaultContext);

export const useUser = () => useContext(UserContext);