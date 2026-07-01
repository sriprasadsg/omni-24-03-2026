import React, { useEffect } from 'react';
import featureHelpContent, { defaultHelp } from '../data/featureHelpContent';
import { HelpCircleIcon, XIcon, CheckIcon } from './icons';

interface FeatureHelpModalProps {
  isOpen: boolean;
  onClose: () => void;
  featureKey: string;
}

export const FeatureHelpModal: React.FC<FeatureHelpModalProps> = ({ isOpen, onClose, featureKey }) => {
  const content = featureHelpContent[featureKey] ?? defaultHelp;

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    const handle = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handle);
    return () => document.removeEventListener('keydown', handle);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label="Feature Help">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal card */}
      <div
        className="relative w-full max-w-lg rounded-2xl overflow-hidden shadow-2xl"
        style={{
          background: 'rgba(12,12,30,0.97)',
          border: '1px solid rgba(255,255,255,0.10)',
          boxShadow: '0 25px 60px rgba(0,0,0,0.6), 0 0 0 1px rgba(0,210,255,0.08)',
        }}
      >
        {/* Header */}
        <div className="flex items-start justify-between p-5 pb-4 border-b border-white/[0.07]">
          <div className="flex items-center gap-3">
            <div
              className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
              style={{ background: 'linear-gradient(135deg, rgba(0,210,255,0.15), rgba(127,0,255,0.15))', border: '1px solid rgba(0,210,255,0.25)' }}
            >
              <HelpCircleIcon size={18} className="text-primary-400" />
            </div>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-widest text-primary-400/70 mb-0.5">Feature Guide</p>
              <h2 className="text-base font-bold text-white leading-tight">{content.title}</h2>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-500 hover:text-slate-200 hover:bg-white/[0.08] transition-all -mr-1 -mt-1"
            aria-label="Close help"
          >
            <XIcon size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4">
          {/* Description */}
          <p className="text-sm text-slate-300 leading-relaxed">{content.description}</p>

          {/* Capabilities */}
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 mb-2.5">Key Capabilities</p>
            <ul className="space-y-2">
              {content.capabilities.map((cap, i) => (
                <li key={i} className="flex items-start gap-2.5">
                  <div className="w-4 h-4 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5"
                    style={{ background: 'rgba(0,210,255,0.12)', border: '1px solid rgba(0,210,255,0.25)' }}>
                    <CheckIcon size={9} className="text-primary-400" />
                  </div>
                  <span className="text-sm text-slate-300">{cap}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Audience */}
          {content.audience && (
            <div className="flex items-center gap-2 pt-1">
              <span className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">Best for</span>
              <span
                className="text-[11px] font-medium px-2.5 py-1 rounded-full"
                style={{ background: 'rgba(127,0,255,0.12)', border: '1px solid rgba(127,0,255,0.25)', color: 'rgba(180,130,255,0.9)' }}
              >
                {content.audience}
              </span>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-white/[0.06]" style={{ background: 'rgba(255,255,255,0.02)' }}>
          <button
            onClick={onClose}
            className="w-full py-2 rounded-xl text-sm font-semibold text-slate-400 hover:text-white hover:bg-white/[0.07] transition-all"
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  );
};

export default FeatureHelpModal;
