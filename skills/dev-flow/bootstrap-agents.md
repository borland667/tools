# Write a fresh repo guide

Use [assets/AGENTS.md.template](assets/AGENTS.md.template) to create a standalone
guide from explicit project requirements and verified facts about the target
repository. This package supplies the authoring procedure and contract; no
other project's guide, policy file or historical task record is an input.
Do not search for, compare, copy or link existing agent guides as a blueprint.

## Establish the target requirements

Determine the project's purpose, component boundaries, supported environment,
verification needs, permitted delivery actions and task-state requirements.
Use user-provided requirements and inspect implementation evidence when
available: code, schemas, build/package scripts, CI, hook configuration and
tracker configuration. For an empty repo, record the decisions that remain
open rather than borrowing another project's conventions.

Active user and repository instructions still govern the authoring task.
Following them does not make them content to import into the generated guide.
If the output destination is occupied, preserve it and prepare the fresh draft
separately; replacing a file requires applicable authorization. Bootstrap does
not authorize rollout, configuration changes or tracker initialization.

## Fill the standalone template

| Template area | What to supply |
|---|---|
| Purpose | The target project's current purpose and scope, without historical project examples. |
| Documentation | Links to relevant target-project documentation when it exists, with reading triggers. Omit absent links; the guide must work without a documentation predecessor. |
| Scope | Directories/components covered by this guide and boundaries between them. State the scope directly instead of referring to another guide for the rules. |
| Code boundaries | Required dependency/state ownership, contract/codegen order, generated-file ownership and data-preservation constraints. Include only requirements that apply to this project. |
| Engineering practices | Select the relevant baseline and profiles from this package's [engineering-practices.md](engineering-practices.md). State concise applicable rules in the output and bind language/tooling, boundaries, budgets and exceptions to this target; no external project guide is needed. |
| Setup | Runtime/package manager, command working directories and environment/service prerequisites established for the target. Mark proposed commands as unverified until checked. |
| Test-first behavior | For new APIs/substantive behavior, bind contract and initial edge-case tests, observed-red checkpoint and blocking green/regression commands using [test-first.md](test-first.md). Keep the reusable procedure in the skill. |
| Dev flow contract | Fill the fenced Markdown section in this package's [repo-contract.md](repo-contract.md) and insert it at `{{DEV_FLOW_CONTRACT_FROM_REPO_CONTRACT_MD}}`. Keep one contract; delete inapplicable rows. |
| Git and delivery | Explicitly authorized actions and decisions still needed: edit, commit, local integration, remote publication, hosted merge and release. Record mode, base branch and sync behavior in the contract; identify CI/deployment effects. |
| Task state | Chosen tracker, its bootstrap/resume commands and where acceptance, evidence and handoff are recorded. Keep guide-only authoring separate from adopting the full workflow. |

The template grants no authority. Use applicable user authorization for each
delivery action; choosing a profile cannot create permission. A consequential
missing choice stays unresolved until the user decides it. Unknown commands,
services or required gates remain explicit gaps, not invented passing checks.

Full dev-flow execution uses Beads for working state and may link a required
team ticket as described in Frame. A standalone guide can use the target's
chosen tracker without adopting the full workflow. Do not initialize or
replace a tracker as a side effect of authoring the guide.

Replace every `{{FIELD}}`, or remove an optional block. For a required unknown,
write the unresolved condition and its effect. Keep reusable process and
agent/model/loop recipes in this package; the output records target-specific
bindings. Do not embed personal paths, account profiles or historical task ids.

## Validate the fresh output

- Resolve every local link from the output's directory. Confirm that all
  required rules and bindings are stated in the output or its target-owned
  implementation/configuration references, without another project as a
  prerequisite. Check for leftover fields and inherited project assumptions.
- Compare commands with their implementation/configuration and run proportionate
  authorized checks in the stated directory with the stated prerequisites.
  For new or changed gates, use this package's
  [deterministic-gates.md](deterministic-gates.md), including actual-trigger
  known-good/known-bad checks. Report unavailable checks honestly.
- Confirm that a fresh reader can determine scope, authority, required checks
  and task-state location from the result. A package, config or draft file's
  presence alone does not prove installation or execution.
- Verify loading in a fresh target-harness session when available; otherwise
  report it as untested. Record drafted, verified and loaded states separately
  in the task tracker, without creating a second Markdown task log.
