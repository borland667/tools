# Bootstrap a repo's agent guide

Use when setting up dev-flow in a repo or consolidating its agent instructions.
The output is a short repo guide with verified bindings, not a copy of the
personal workflow. Start with [assets/AGENTS.md.template](assets/AGENTS.md.template).
This authoring procedure does not authorize rollout to other repositories.

## Discover ownership before writing

- Inspect applicable ancestor/root/nested guides, `AGENTS.override.md`, linked
  `CLAUDE.md`, symlinks, configured instruction fallbacks and managed blocks.
  Resolve the current checkout and each guide's scope. Treat vendor guides,
  plugin fixtures, translations and old worktree variants as reference data,
  not current project policy. Deduplicate identical copies when comparing.
- Preserve the existing source of truth. If `CLAUDE.md` owns the rules, a thin
  `AGENTS.md` pointer may be the right output. If a working compatibility shim
  or symlink exists, retain it. Do not replace managed sections, flatten nested
  rules, or silently reconcile contradictory policies. Record the conflict and
  resolve only what the current authority covers.
- Check the target harness's actual discovery. Codex considers an override
  before `AGENTS.md` in a directory; `CLAUDE.md` needs an explicit reference or
  configured fallback. Do not change global discovery settings to make this
  bootstrap work. See the [Codex instruction guide](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

## Fill from the repo, not from another project's defaults

Inspect the documentation map, build/package scripts, CI and hook registration,
ignore rules, current Git/worktree state and tracker configuration. Carry over
only facts needed to act correctly in this repo:

| Template area | What to supply |
|---|---|
| Purpose and documentation | Current scope; relative links with task-specific reading triggers. Put roadmaps, long implementation snapshots and tutorials in their owning docs. |
| Guidance ownership | Canonical file and scoped exceptions; for a multi-repo workspace, point to child guides instead of imposing one child's Git/build policy on all children. |
| Code boundaries | Actual dependency/state ownership, schema/codegen order, generated files and narrowly relevant data-preservation rules. Link detailed quality/review catalogs. |
| Setup | Supported runtime/package manager, working directory, environment/service prerequisites and existing setup command or doc. Never embed secret values or personal filesystem paths. |
| Dev flow contract | Insert the filled fenced Markdown section from [repo-contract.md](repo-contract.md) at `{{DEV_FLOW_CONTRACT_FROM_REPO_CONTRACT_MD}}`. Keep one contract, deleting inapplicable rows. Include command working directories, ordered prerequisites and available gate/config links. |
| Git and delivery | Existing grants/restrictions: edit, commit, local integration, remote publication, hosted merge and release. Record mode, actual base branch and local-only/remote sync in the contract. Identify automatic CI/deploy effects before calling publication routine. |
| Task state | Tracker entry point, session bootstrap/resume and where acceptance/evidence/handoff live. Link the maintained tracker guide rather than copying a vendor manual. |

Direct mode and standing commit/integration authority must come from applicable
instructions or the user; choosing a template value cannot create permission.
Preserve narrower per-repo restrictions and broader applicable grants. Resolve
missing facts from repository evidence when possible; ask only for a consequential
choice that evidence and existing authority cannot settle. Inferred commands
are proposals until checked. Mark unverified commands/prerequisites explicitly,
and keep a missing required gate unresolved rather than inventing a passing one.

Dev-flow uses Beads for working state. When a team requires another tracker,
keep that record and its policy; link the bead as described in Frame. Bootstrap
does not authorize tracker initialization or replacement. Resolve a prohibition
or incompatible tracker policy before adopting dev-flow; a standalone repo
guide can retain its existing tracker without adopting this skill.

Replace every `{{FIELD}}`, or remove an optional block. If a required fact is
unknown, write the concrete unresolved condition and effect instead of leaving
a placeholder. Omit absent doc links; do not create speculative docs or commands
just to fill the template. For an existing well-scoped guide, add only the
missing bindings. Keep process, personal agent/model catalogs and loop recipes
in shared skills; include repo-specific bindings only when actually used.

## Validate the resulting guide

- Follow every local link from the guide's directory and compare its commands
  with their owning scripts/configs. Check nested scopes and canonical pointers
  for contradictions, loops and accidentally hidden root instructions. Preserve
  unrelated content and managed markers.
- Run proportionate, authorized verification in the stated working directory
  with its prerequisites. A setup doc link, a config file or a copied command is
  not execution evidence. For new/changed gates, use
  [deterministic-gates.md](deterministic-gates.md), including actual-trigger
  known-good/known-bad checks. Record unavailable checks honestly.
- Inspect the final diff for leftover fields, invented grants, secrets, private
  paths, stale task ids and duplicated process. Check that a fresh agent can
  locate the tracker, determine what it may do and find the required checks.
- Confirm discovery in a fresh target-harness session when available; an
  already-running session does not prove newly written guidance was loaded.
  Otherwise report instruction loading as untested. Distinguish a drafted guide,
  a verified guide and an adopted/loaded guide in the task record.

Use task evidence to refine the guide later. Store comparison findings and
remaining setup work in the tracker, not in a second Markdown task log.
