import React from 'react';

// RED-phase stub: the behavior lands in the next commit.
export const PartnerScreenPicker: React.FC<{
  mode: 'ceiling' | 'customer';
  ceiling?: string[];
  unrestricted?: boolean;
  value: string[];
  kept?: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
}> = () => null;
