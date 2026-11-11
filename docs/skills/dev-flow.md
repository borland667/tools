# Dev-flow skill package

`skills/dev-flow/` is a standalone development workflow package.
Copy the entire folder: its entrypoint needs the review,
gate, evidence and bootstrap references beside it. The bundled `LICENSE` keeps
the repository's MIT license with a standalone copy.

## Contents and requirements

| Resource | Purpose |
|---|---|
| `SKILL.md` | Discovery, authority, stages, lanes and optional integrations |
| `repo-contract.md` | Single template for repo commands and delivery bindings |
| `engineering-practices.md` | Language-independent architecture/quality baseline and conditional stack specifics |
| `review-agents.md` | Review coverage, independence, prompts and launch recipes |
| `deterministic-gates.md` | Authoring and proving hooks and other repeatable gates |
| `evidence-and-learning.md` | Resume, baseline, revision-bound evidence and handoff |
| `bootstrap-agents.md` | Author a fresh guide from target requirements and verified facts |
| `assets/AGENTS.md.template` | Standalone repo-guide template; not active instructions |

Full workflow execution requires Git, the Beads `bd` CLI, a configured task
workspace and the target repo's build/test dependencies. Guide-only authoring
uses the repo's existing tracker. Beads and its skill are not bundled in this
folder; follow the target repo's Beads setup instructions when adopting the
workflow. Do not replace an existing team tracker or initialize one merely
because this folder was installed.

Architecture and engineering rules are shared in `engineering-practices.md`.
Fresh guides include the applicable baseline and target-specific language,
tooling, ownership and budget bindings. Profiles are conditional: a shell CLI
does not inherit a web service's API, queue or schema machinery. Additional
languages use the same binding method; commands and limits come from target
requirements and verified code/configuration, not another project's guide.

Herdr orchestration and oMLX/local harnesses are optional. They need separate
installation, host support, authentication/model setup and authorization.
Without them, use native Git worktrees and the documented independent review
handoff/fallback. Missing required model independence keeps review pending;
package installation cannot satisfy it. The package contains no credentials,
account launchers, model weights or machine-specific model defaults.

## Local installation

These are local skill-folder instructions, not a published plugin or a global
configuration migration. For Codex, the current user scope is
`~/.agents/skills/dev-flow`; project scope is `.agents/skills/dev-flow`. Codex
supports symlinked skill directories. See [official OpenAI skill documentation](https://learn.chatgpt.com/docs/build-skills).

For Claude Code terminal sessions, copy the complete folder to
`~/.claude/skills/dev-flow` (personal) or `.claude/skills/dev-flow` (project),
using the active profile's documented scope. These local paths do not install
the skill into Cowork/cloud sessions. See [Claude Code skills](https://code.claude.com/docs/en/skills).

First inspect the chosen location and any other active skill named `dev-flow`,
including another local installation. Preserve local edits and choose the
source to keep before changing a link; duplicate installations are not merged.
Preparing this package does not change an existing installation automatically.

From the tools repo root, this Codex user-scope example refuses an occupied
target, including a dangling symlink:

```bash
(
  skill_source="$(pwd -P)/skills/dev-flow"
  skill_target="$HOME/.agents/skills/dev-flow"
  test -f "$skill_source/SKILL.md" || exit 1
  if test -e "$skill_target" || test -L "$skill_target"; then
    printf '%s\n' "Target already exists; inspect it before migration." >&2
    exit 1
  fi
  mkdir -p "$(dirname "$skill_target")" || exit 1
  ln -s "$skill_source" "$skill_target"
)
```

For a standalone snapshot, use `cp -R "$skill_source" "$skill_target"`
instead of the final `ln -s` inside the same guarded block. A symlink tracks
changes to its source checkout; a copy needs deliberate updates. Keep symlinks
pointing at a retained checkout, not a disposable task worktree.

Confirm the installed folder and references, then verify discovery in a fresh
target-harness session: invoke `$dev-flow` in Codex or `/dev-flow` in Claude
Code and check the source that loaded. This is separate from static package
validation. No install command here grants commits, pushes, model calls or
other workflow actions. Reconcile repo bindings before running a task.

## Validation and maintenance

From the tools repo root, Python 3.9+ and its standard library are sufficient:

```bash
python3 scripts/validate_dev_flow.py --help
python3 scripts/validate_dev_flow.py
python3 -B -m unittest discover -s tests/dev_flow -v
```

The validator also accepts a relocated/copied package:

```bash
python3 scripts/validate_dev_flow.py --skill-dir /path/to/copied/dev-flow
```

This is an offline manual package gate. It checks required resources, the
entrypoint identity/metadata fields, relative-link completeness/confinement,
symlinks and known machine/account binding patterns. It returns 1
on a violation and 0 on success. It does not install hooks, parse every YAML
feature, validate Markdown anchors, scan arbitrary credential formats or check
remote links. Audit the staged diff for secrets separately. It neither needs
nor contacts Beads, models or external services.

The tests copy the actual bundle to temporary locations and demonstrate valid
packages passing and missing assets, external dependencies, machine bindings
and incorrect metadata failing. Installation commands should also be exercised
with temporary destinations, including existing and dangling-link cases,
before changing them. If registering this command as a commit/CI gate later,
follow `deterministic-gates.md` and test that actual trigger and input scope.

Update the entrypoint and its owning references together; keep the contract
template unique and preserve repo-specific choices in generated guides. Review
behavior with realistic scenarios when instructions change. Package checks
and isolated probes do not prove a complete workflow run, target-harness
loading, live hook/CI enforcement or quality gains from multiple models.
