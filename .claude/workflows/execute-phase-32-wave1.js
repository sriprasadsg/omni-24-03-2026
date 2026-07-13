export const meta = {
  name: 'execute-phase-32',
  description: 'Execute Phase 32 plans using wave-based parallel execution.',
  phases: [
    { title: 'Discover Plans', detail: 'Find all PLAN.md files in the phase directory.' },
    { title: 'Analyze Dependencies', detail: 'Parse plans and determine wave dependencies.' },
    { title: 'Execute Wave 1', detail: 'Spawn subagents for Wave 1 plans.' },
    { title: 'Verify Wave 1', detail: 'Collect results and verify Wave 1 completion.' },
  ],
};

phase('Discover Plans');
log('Finding all PLAN.md files in .planning/phases/32-cloud-and-saas-provider-expansion/');
const planFiles = await agent('Find all PLAN.md files in .planning/phases/32-cloud-and-saas-provider-expansion/', {
  agentType: 'caveman:cavecrew-investigator',
  schema: {
    type: 'array',
    items: {
      type: 'string',
    },
  },
  prompt: 'List all paths matching `**/*-PLAN.md` within the directory `.planning/phases/32-cloud-and-saas-provider-expansion/`',
});

if (!planFiles || planFiles.length === 0) {
  log('No PLAN.md files found. Exiting.');
  return { status: 'failed', message: 'No plans found for Phase 32.' };
}

log(`Found ${planFiles.length} plan files: ${planFiles.join(', ')}`);

phase('Analyze Dependencies');
log('Analyzing dependencies and grouping plans into waves...');
const plans = await parallel(planFiles.map(file => async () => {
  const content = await agent(`Read content of ${file}`, {
    agentType: 'caveman:cavecrew-investigator',
    model: 'claude-opus-4-8',
    schema: { type: 'string' },
    prompt: `Read the content of ${file}`,
    files_to_read: [file],
  });
  // Simple parsing for now, assuming no complex dependencies for initial waves
  // Later: enhance with proper frontmatter parsing for `wave` and `depends_on`
  const waveMatch = content.match(/wave:\s*(\d+)/);
  const wave = waveMatch ? parseInt(waveMatch[1], 10) : 1; // Default to Wave 1

  return { file, wave, content };
}));

const wave1Plans = plans.filter(p => p.wave === 1);

if (wave1Plans.length === 0) {
  log('No plans found for Wave 1. Exiting.');
  return { status: 'failed', message: 'No plans found for Wave 1 in Phase 32.' };
}

log(`Found ${wave1Plans.length} plans for Wave 1: ${wave1Plans.map(p => p.file).join(', ')}`);

phase('Execute Wave 1');
log('Executing Wave 1 plans...');
const wave1Results = await parallel(wave1Plans.map(plan => async () => {
  log(`Executing plan: ${plan.file}`);
  return await agent(`Execute plan: ${plan.file}`, {
    agentType: 'gsd-executor',
    model: 'claude-opus-4-8',
    isolation: 'worktree', // Ensure isolated execution per plan
    prompt: `Execute the plan described in ${plan.file}.`,
    args: {
      plan_file: plan.file,
    },
  });
}));

phase('Verify Wave 1');
log('Verifying Wave 1 completion...');
const allSuccessful = wave1Results.every(result => result && result.status === 'completed');

if (allSuccessful) {
  log('Wave 1 execution completed successfully.');
  return { status: 'completed', message: 'Phase 32 Wave 1 executed successfully.' };
} else {
  log('Wave 1 execution failed for some plans.');
  return { status: 'failed', message: 'Phase 32 Wave 1 execution failed.' };
}
