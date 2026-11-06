/**
 * ACTV-08: Autonomous Ops copy never uses the banned terms (frontend side).
 *
 * The rules and the explicit list of scanned files live in shared/autonomous-ops-banned-terms.json;
 * backend/tests/test_autonomous_ops_copy.py reads the same file and scans the backend files and the
 * catalogue label. This side scans the frontend files. Every listed file must exist, and each rule
 * has negative controls proving it fires.
 *
 * Note: `npm run build` is vite build and runs no tests; this suite is part of the project test gate
 * (npx vitest run src/__tests__) together with the backend pytest suite.
 */
import { afterAll, describe, it, expect } from 'vitest';
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, relative, resolve } from 'node:path';
import rulesFile from '../../shared/autonomous-ops-banned-terms.json';

const ROOT = resolve(__dirname, '../..');

interface Rule { id: string; pattern: string; flags: string; unlessLineContains?: string }

// The same list is hard-coded in the pytest side. If either side drifts from the JSON, it fails.
const EXPECTED_FILES = [
  'backend/autonomous_ops/messages.py',
  'backend/autonomous_ops/views.py',
  'backend/autonomous_ops/response_messages.py',
  'backend/autonomous_ops/response_views.py',
  'backend/autonomous_ops/incident_views.py',
  'backend/autonomous_ops/health_messages.py',
  'backend/autonomous_ops/selfheal.py',
  'backend/autonomous_ops_endpoints.py',
  'backend/autonomous_ops_platform_endpoints.py',
  'backend/watchdog_ingest_endpoints.py',
  'backend/autonomous_ops_retention_endpoints.py',
  'backend/autonomous_ops_response_endpoints.py',
  'backend/autonomous_ops_response_platform_endpoints.py',
  'services/autonomousOpsApi.ts',
  'services/autonomousOpsIncidentsApi.ts',
  'contexts/AutonomousOpsStatusContext.tsx',
  'components/AutonomousOpsActivity.tsx',
  'components/AutonomousOpsActivityList.tsx',
  'components/AutonomousOpsRowActions.tsx',
  'components/AutonomousOpsDecisions.tsx',
  'components/AutonomousOpsIncidentCard.tsx',
  'components/AutonomousOpsStatusCard.tsx',
  'components/AutonomousOpsStopDialog.tsx',
  'components/AutonomousOpsStopBanner.tsx',
  'components/AutonomousOpsHealthBanners.tsx',
  'components/AutonomousOpsHealthChips.tsx',
  'components/AutonomousOpsPlatformHealth.tsx',
  'components/AutonomousOpsHealthCards.tsx',
  'components/AutonomousOpsRetentionReview.tsx',
  'components/AutonomousOpsRetentionConfirmDialog.tsx',
  'components/AutonomousOpsResponseSettings.tsx',
  'components/AutonomousOpsResponseSettingsDialogs.tsx',
  'components/AutonomousOpsResponseSettingsPlatform.tsx',
  'components/SwarmDashboard.tsx',
];

// Whole directories are walked recursively, so a file added later is covered without a list edit (UI-SPEC DEV-4).
// The same list is hard-coded in the pytest side. If either side drifts from the JSON, it fails.
const EXPECTED_DIRECTORIES = [
  'backend/autonomous_ops/rollout',
  'components/patchRollouts',
  'services/patchRollouts',
];

const RULES: Rule[] = rulesFile.rules as Rule[];
const DIRECTORIES: string[] = (rulesFile as unknown as { directories: string[] }).directories;
const FRONTEND_DIRECTORIES = DIRECTORIES.filter(d => !d.startsWith('backend/'));
const FRONTEND_FILES = rulesFile.files.filter(f => !f.startsWith('backend/'));

/** (line number, rule id, line) for every line that breaks a rule; the exception is per line. */
function violations(text: string, rules: Rule[]): Array<[number, string, string]> {
  const compiled = rules.map(rule => ({ rule, re: new RegExp(rule.pattern, rule.flags) }));
  const found: Array<[number, string, string]> = [];
  text.split(/\r?\n/).forEach((line, index) => {
    for (const { rule, re } of compiled) {
      if (rule.unlessLineContains && line.toLowerCase().includes(rule.unlessLineContains.toLowerCase())) continue;
      if (re.test(line)) found.push([index + 1, rule.id, line.trim()]);
    }
  });
  return found;
}

/** Missing listed files are their own failure, never a silent skip. */
function scanFiles(files: string[], rules: Rule[], root = ROOT): { missing: string[]; problems: string[] } {
  const missing: string[] = [];
  const problems: string[] = [];
  for (const rel of files) {
    const path = resolve(root, rel);
    if (!existsSync(path)) { missing.push(rel); continue; }
    for (const [n, id, line] of violations(readFileSync(path, 'utf-8'), rules)) problems.push(`${rel}:${n} [${id}] ${line}`);
  }
  return { missing, problems };
}

describe('ACTV-08 rules file', () => {
  it('has at least five unique rules with valid patterns', () => {
    const ids = RULES.map(r => r.id);
    expect(ids.length).toBeGreaterThanOrEqual(5);
    expect(new Set(ids).size).toBe(ids.length);
    for (const rule of RULES) {
      expect(rule.pattern).not.toBe('');
      expect(rule.flags === '' || rule.flags === 'i').toBe(true);
      expect(() => new RegExp(rule.pattern, rule.flags)).not.toThrow();
    }
    expect(rulesFile.catalogueViews).toEqual(['autonomousOps']);
  });

  it('lists the agreed files and keeps other screens, the Windows Autopilot screen and .planning out of scope', () => {
    expect(rulesFile.files).toEqual(EXPECTED_FILES);
    for (const rel of rulesFile.files) {
      expect(rel.startsWith('.planning')).toBe(false);
      expect(rel.toLowerCase()).not.toContain('autopilot');
      expect(rel.endsWith('AutonomousOpsLog.tsx')).toBe(false);
    }
  });

  it('every listed file exists', () => {
    expect(scanFiles(rulesFile.files, RULES).missing).toEqual([]);
  });

  it('reports a missing listed file instead of skipping it', () => {
    const result = scanFiles(['components/NoSuchAutonomousOpsFile.tsx'], RULES);
    expect(result.missing).toEqual(['components/NoSuchAutonomousOpsFile.tsx']);
    expect(result.problems).toEqual([]);
  });
});

describe('ACTV-08 real copy', () => {
  it('the frontend files pass every rule', () => {
    const { missing, problems } = scanFiles(FRONTEND_FILES, RULES);
    expect(missing).toEqual([]);
    expect(problems).toEqual([]);
  });

  it('scans at least the status card, dialog, banner, activity screen, client and poller', () => {
    expect(FRONTEND_FILES).toHaveLength(21);
  });
});

const FLAGGED: Record<string, string[]> = {
  asi: ['Our ASI engine', 'ASI.', '(ASI)'],
  agi: ['AGI inside', 'an AGI feature'],
  autopilot: ['autopilot mode', 'Autopilot', 'AUTOPILOT'],
  'fully-autonomous': ['fully autonomous', 'fully-autonomous', 'Fully Autonomous operations'],
  rollback: ['we roll back', 'rollback', 'rolled back', 'rolling-back', 'Roll-back', 'rolling back the change'],
};
const PASSING: Record<string, string[]> = {
  asi: ['basic', 'magic', 'classify', 'Asia', 'asi'],
  agi: ['magic', 'imagine', 'again'],
  autopilot: ['autonomous', 'automatic actions'],
  'fully-autonomous': ['autonomous within limits', 'fully supported'],
  rollback: ['rollback where supported', 'Rollback Where Supported', 'rolled_back', 'rollback_ransomware',
    'rotate_key_rollback', 'undo', 'roller'],
};

describe('ACTV-08 negative controls', () => {
  it('every rule in the file has a control, and no control names a missing rule', () => {
    const ids = RULES.map(r => r.id).sort();
    expect(Object.keys(FLAGGED).sort()).toEqual(ids);
    expect(Object.keys(PASSING).sort()).toEqual(ids);
  });

  for (const id of Object.keys(FLAGGED)) {
    it(`${id}: fires on its examples`, () => {
      const rules = RULES.filter(r => r.id === id);
      expect(rules).toHaveLength(1);
      for (const text of FLAGGED[id]) {
        expect(violations(text, rules).map(v => v[1]), text).toEqual([id]);
      }
    });

    it(`${id}: leaves its look-alikes alone`, () => {
      const rules = RULES.filter(r => r.id === id);
      for (const text of PASSING[id]) expect(violations(text, rules), text).toEqual([]);
    });
  }

  it('"where supported" exempts only its own line', () => {
    const text = 'Undo works.\nRollback where supported.\nThen we roll back everything.';
    expect(violations(text, RULES).map(v => [v[0], v[1]])).toEqual([[3, 'rollback']]);
  });
});

/** .py under backend/, .ts and .tsx everywhere else. */
function scannable(relDir: string, name: string): boolean {
  return relDir.startsWith('backend/') ? name.endsWith('.py') : /\.tsx?$/.test(name);
}

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === '__pycache__') continue;
    const full = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walk(full));
    else out.push(full);
  }
  return out.sort();
}

/** A directory that is missing, or holds no scannable file, is its own failure, never a silent pass. */
function scanDirectories(dirs: string[], rules: Rule[], root = ROOT): { missingOrEmpty: string[]; problems: string[] } {
  const missingOrEmpty: string[] = [];
  const problems: string[] = [];
  for (const relDir of dirs) {
    const base = resolve(root, relDir);
    const files = existsSync(base) ? walk(base).filter(f => scannable(relDir, f)) : [];
    if (files.length === 0) { missingOrEmpty.push(relDir); continue; }
    for (const file of files) {
      for (const [n, id, line] of violations(readFileSync(file, 'utf-8'), rules)) {
        problems.push(`${relative(root, file).split('\\').join('/')}:${n} [${id}] ${line}`);
      }
    }
  }
  return { missingOrEmpty, problems };
}

describe('ACTV-08 directories', () => {
  it('lists the agreed directories', () => {
    expect(DIRECTORIES).toEqual(EXPECTED_DIRECTORIES);
    for (const rel of DIRECTORIES) {
      expect(rel.startsWith('.planning')).toBe(false);
      expect(rel.toLowerCase()).not.toContain('autopilot');
      expect(rel.endsWith('/')).toBe(false);
    }
  });

  it('every listed directory exists and holds a scannable file', () => {
    expect(scanDirectories(DIRECTORIES, RULES).missingOrEmpty).toEqual([]);
  });

  it('every .ts and .tsx file under the frontend directories passes every rule', () => {
    expect(FRONTEND_DIRECTORIES).toEqual(['components/patchRollouts', 'services/patchRollouts']);
    const { missingOrEmpty, problems } = scanDirectories(FRONTEND_DIRECTORIES, RULES);
    expect(missingOrEmpty).toEqual([]);
    expect(problems).toEqual([]);
  });

  describe('negative controls', () => {
    const temp = mkdtempSync(join(tmpdir(), 'copy-gate-'));
    const put = (rel: string, text: string) => {
      const full = join(temp, rel);
      mkdirSync(join(full, '..'), { recursive: true });
      writeFileSync(full, text);
    };
    afterAll(() => rmSync(temp, { recursive: true, force: true }));

    it('reports a banned term planted in a nested file of a scanned directory', () => {
      put('components/patchRollouts/nested/Copy.tsx', "const a = 'Revert where supported.';\nconst b = 'We roll back the patch.';\n");
      put('components/patchRollouts/notes.md', 'Autopilot in a file type that is not scanned.\n');
      const { missingOrEmpty, problems } = scanDirectories(['components/patchRollouts'], RULES, temp);
      expect(missingOrEmpty).toEqual([]);
      expect(problems).toEqual(["components/patchRollouts/nested/Copy.tsx:2 [rollback] const b = 'We roll back the patch.';"]);
    });

    it('reports an empty or missing directory instead of skipping it', () => {
      mkdirSync(join(temp, 'services/patchRollouts'), { recursive: true });
      put('services/patchRollouts/readme.md', 'not a scannable type\n');
      const result = scanDirectories(['services/patchRollouts', 'services/noSuchDirectory'], RULES, temp);
      expect(result.missingOrEmpty).toEqual(['services/patchRollouts', 'services/noSuchDirectory']);
      expect(result.problems).toEqual([]);
    });
  });
});
