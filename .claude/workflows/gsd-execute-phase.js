export const meta = {
  name: 'gsd-execute-phase',
  description: 'Execute all plans in a phase using wave-based parallel execution.',
  phases: [
    { title: 'Discover Plans' },
    { title: 'Analyze Dependencies' },
    { title: 'Execute Wave' },
    { title: 'Check Completion' },
    { title: 'Update State' },
  ],
}

phase('Discover Plans')
const { phase_number, all_plans, active_flags } = await agent(
  `Discover plans and active flags for phase ${args}.`,
  {
    agentType: 'gsd-executor',
    schema: {
      type: 'object',
      properties: {
        phase_number: { type: 'number' },
        all_plans: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              plan_id: { type: 'string' },
              wave: { type: 'number' },
              dependencies: { type: 'array', items: { type: 'string' } },
              is_gap_closure: { type: 'boolean' },
              status: { type: 'string', enum: ['pending', 'completed'] },
            },
            required: ['plan_id', 'wave', 'status'],
          },
        },
        active_flags: {
          type: 'object',
          properties: {
            wave: { type: 'number', nullable: true },
            gaps_only: { type: 'boolean' },
            interactive: { type: 'boolean' },
          },
        },
      },
      required: ['phase_number', 'all_plans', 'active_flags'],
    },
  }
)

log(`Discovered ${all_plans.length} plans for Phase ${phase_number}.`)
log(`Active flags: ${JSON.stringify(active_flags)}`)

const pending_plans = all_plans.filter((p) => p.status === 'pending')

if (pending_plans.length === 0) {
  log(`Phase ${phase_number} already complete.`)
  await agent(`Update phase ${phase_number} status to 'Completed'.`, {
    agentType: 'gsd-executor',
  })
  return { status: 'Phase Already Completed', phase_number }
}

phase('Analyze Dependencies')
const plans_to_execute = pending_plans.filter((plan) => {
  if (active_flags.wave && plan.wave !== active_flags.wave) {
    return false
  }
  if (active_flags.gaps_only && !plan.is_gap_closure) {
    return false
  }
  return true
})

if (plans_to_execute.length === 0) {
  log(`No plans to execute for Phase ${phase_number} with current flags.`)
  return { status: 'No Plans to Execute', phase_number }
}

const dependency_satisfied_plans = plans_to_execute.filter((plan) =>
  (plan.dependencies || []).every((dep_id) =>
    all_plans.some((p) => p.plan_id === dep_id && p.status === 'completed')
  )
)

if (dependency_satisfied_plans.length === 0) {
  log(`No plans with satisfied dependencies to execute for Phase ${phase_number}.`)
  return { status: 'No Plans with Satisfied Dependencies', phase_number }
}

phase('Execute Wave')
if (active_flags.interactive) {
  for (const plan of dependency_satisfied_plans) {
    await agent(`Execute plan ${plan.plan_id} interactively.`, {
      agentType: 'gsd-executor',
      args: { plan_id: plan.plan_id, phase_number: phase_number },
    })
    await AskUserQuestion({
      reason: `Checkpoint after plan ${plan.plan_id}`,
      questions: [
        {
          question: `Plan ${plan.plan_id} execution complete. Continue to next plan?`,
          header: 'Continue?',
          options: [{ label: 'Yes', description: 'Continue' }],
          multiSelect: false,
        },
      ],
    })
  }
} else {
  await parallel(
    dependency_satisfied_plans.map(
      (plan) => () =>
        agent(`Execute plan ${plan.plan_id}.`, {
          agentType: 'gsd-executor',
          args: { plan_id: plan.plan_id, phase_number: phase_number },
          label: `Plan ${plan.plan_id}`,
        })
    )
  )
}

phase('Check Completion')
const remaining_pending_plans = all_plans.filter((p) => p.status === 'pending').length
if (remaining_pending_plans === 0) {
  log(`All plans for Phase ${phase_number} completed. Updating phase status.`)
  await agent(`Update phase ${phase_number} status to 'Completed'.`, {
    agentType: 'gsd-executor',
  })
  return { status: 'Phase Completed', phase_number }
} else {
  log(
    `Phase ${phase_number} has ${remaining_pending_plans} pending plans remaining.
    `
  )
  await agent(`Update phase ${phase_number} status to 'In Progress'.`, {
    agentType: 'gsd-executor',
  })
  return { status: 'Phase In Progress', phase_number, remaining_pending_plans }
}