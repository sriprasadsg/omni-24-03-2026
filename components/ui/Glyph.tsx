import React from 'react';
import {
  type LucideIcon, Activity, AlertTriangle, ArrowLeftRight, ArrowUp, BarChart3, Bell, Bird, Bot, Brain, Building2, Calendar, CheckCircle2,
  ClipboardList, Clock, Cloud, Container, CreditCard, Database, Download, Eye, FileText, Fingerprint, Flame,
  FlaskConical, Folder, Globe, HardDrive, Info, Key, KeyRound, Laptop, Lightbulb, Link, Lock, LockKeyhole, LockOpen, Mail, Map,
  MessageSquare, Monitor, Network, Package, Pencil, Pin, Play, Plug, Plus, Puzzle, RadioTower, RefreshCw, Rocket,
  Save, Search, Server, Settings, Shield, Siren, Skull, Smartphone, Sparkles, Star, Tag, Target, Ticket, Timer,
  Trash2, TrendingDown, TrendingUp, Upload, User, Users, Wrench, XCircle, Zap,
} from 'lucide-react';

/** Emoji older screens used as icons, and the icon that replaces each (the design system draws icons, never emoji). */
const ICONS: Record<string, LucideIcon> = {
  '🔍': Search, '🔎': Search, '📋': ClipboardList, '🔑': KeyRound, '🗝': Key, '🔒': Lock, '🔐': LockKeyhole,
  '⚡': Zap, '🌐': Globe, '🌍': Globe, '📊': BarChart3, '📈': TrendingUp, '📉': TrendingDown, '🛡': Shield,
  '🖥': Monitor, '💻': Laptop, '📱': Smartphone, '📡': RadioTower, '☁': Cloud, '📦': Package, '🐳': Container,
  '🎫': Ticket, '⚙': Settings, '💡': Lightbulb, '🗄': Database, '💾': HardDrive, '❌': XCircle, '✅': CheckCircle2,
  '⚠': AlertTriangle, '🚨': Siren, '🔥': Flame, '🧠': Brain, '🤖': Bot, '🎯': Target, '💬': MessageSquare,
  '📤': Upload, '📥': Download, '🚀': Rocket, '🔗': Link, '🔄': RefreshCw, '📄': FileText, '📝': Pencil,
  '✏': Pencil, '📁': Folder, '📧': Mail, '✉': Mail, '🪤': Bird, '🐦': Bird, '🔔': Bell, '👤': User, '👥': Users,
  '🧪': FlaskConical, '🐛': Activity, '🦠': Skull, '💀': Skull, '🔧': Wrench, '🛠': Wrench, '⏱': Timer,
  '⏰': Clock, '🕐': Clock, '📅': Calendar, '🏷': Tag, '🗑': Trash2, '➕': Plus, '▶': Play, '🏢': Building2,
  '🧩': Puzzle, '📌': Pin, '⭐': Star, '✨': Sparkles, '🔌': Plug, '🗺': Map, '💳': CreditCard, '🖧': Network,
  '🗂': Folder, 'ℹ': Info, '👁': Eye, '🧬': Fingerprint, '🖲': Server, '🔓': LockOpen, '↔': ArrowLeftRight,
  '⬆': ArrowUp,
};

/** Coloured-circle emoji used as status dots. */
const DOTS: Record<string, string> = {
  '🔴': 'text-red-500', '🟠': 'text-orange-500', '🟡': 'text-amber-400', '🟢': 'text-emerald-500',
  '🔵': 'text-blue-500', '🟣': 'text-purple-500', '⚪': 'text-gray-400', '⚫': 'text-gray-600', '🔷': 'text-blue-500',
};

/** Draws the icon for an emoji an older screen used as one; a character it does not know renders as itself,
 *  and no value (an icon table without an entry) renders nothing. */
export const Glyph: React.FC<{ e?: string | null; size?: number | string; className?: string }> = ({ e, size = '1em', className = '' }) => {
  if (!e) return null;
  const key = e.replace(/️/g, '').trim();
  const dot = DOTS[key];
  if (dot) {
    return <span aria-hidden="true" className={`inline-block h-[0.6em] w-[0.6em] shrink-0 rounded-full bg-current align-middle ${dot} ${className}`} />;
  }
  const Icon = ICONS[key];
  if (!Icon) return <>{e}</>;
  return <Icon size={size} aria-hidden="true" className={`inline-block shrink-0 align-[-0.125em] ${className}`} />;
};

/** True when `e` is an emoji Glyph draws as an icon or a dot. */
export const hasGlyph = (e?: string | null) => {
  const key = (e ?? '').replace(/️/g, '').trim();
  return key in ICONS || key in DOTS;
};
