# Dev-flow skill package

`skills/dev-flow/` is the canonical source for this development workflow. Keep
the entrypoint, references, templates, installation and validation documentation
together here. Other local installations use symlinks to this retained tools
checkout. Maintain each file once; do not synchronize independent copies. The
bundled `LICENSE` preserves the repository's MIT license for portable distribution.

## Contents and requirements

| Resource | Purpose |
|---|---|
| `SKILL.md` | Discovery, authority, stages, lanes and optional integrations |
| `task-intake.md` | Task-type routing through initial Design or Diagnose, exit evidence and re-entry |
| `installation.md` / `validation.md` | Canonical setup and package-check documentation |
| `local.example.md` / `.gitignore` | Portable host-binding example and private-local exclusion |
| `repo-contract.md` | Single template for repo commands and delivery bindings |
| `ticket-mapping.md` | 1:1 external ticket identity, field/status ownership and authorized reconciliation protocol; no installed sync adapter |
| `engineering-practices.md` | Language-independent architecture/quality baseline and conditional stack specifics |
| `test-first.md` | Initial contract/edge-case tests, red-to-green checkpoints and blocking test gates |
| `acceptance-exercise.md` | Exercising delivered behavior through its real entry point, lane depth, findings and limits |
| `review-agents.md` | Review coverage, independence, prompts and launch recipes |
| `model-selection.md` | Dated frontier/local role recommendations, effort, independence and qualification limits |
| `local-second-opinions.md` | Supervised Flash/oMLX/Splash review, limits and gate authority |
| `hermes-coordinator.md` / `assets/hermes-coordinator.md` | Hermes coordinator protocol and linked profile instructions |
| `scripts/run_worker.py` / `worker-launcher.md` | Bounded Claude/Codex jobs with per-task profile selection |
| `deterministic-gates.md` | Authoring and proving hooks and other repeatable gates |
| `invariant-guards.md` | Guard patterns for hard invariants, their self-tests and per-language tools |
| `assets/PR.md.template` | Default PR body when the repo has none |
| `evidence-and-learning.md` | Resume, baseline, revision-bound evidence and handoff |
| `tmp-docs.md` / `assets/TMP.md.template` | Categorized local working docs, Beads links, promotion, archive and retention |
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

New APIs and substantive behavior changes use test-first development: define
the contract and initial relevant edge-case matrix, write and run the tests
before production behavior, verify they fail for the intended missing behavior,
then implement to green and refactor. Required tests and regressions block
delivery through repo-owned commands/triggers. Known material risks need initial
cases; new discoveries add tests before fixes. Coverage percentages and model
opinions do not establish test adequacy. Installing this skill does not install
hooks or CI enforcement; each target binds and proves those separately.

Herdr or Hermes coordination (interchangeable) and oMLX/local harnesses are optional. They need separate
installation, host support, authentication/model setup and authorization.
Without them, use native Git worktrees and the documented independent review
handoff/fallback. Missing required model independence keeps review pending;
package installation cannot satisfy it. The package contains no credentials,
account launchers, model weights or machine-specific model defaults.

The supervised Flash-through-oMLX/Splash integration is enabled by a private
host profile: exact advertised model id, loopback endpoint, confirmed Splash
backend, transport, resource limits and qualification evidence. The portable
skill describes when and how to use that binding without selecting a global
default. Its bounded review remains advisory; the lead confirms findings and
deterministic gates keep their declared blocking policy. Required hosted and
independent deep/security reviews still apply. No live model call is installed
as a hook or CI gate.

The tools repo also owns optional qualification helpers, documented at
`docs/scripts/evaluate_local_models.md` and `docs/scripts/evaluate_model_harness.md`.
They are separate reusable tools, not dependencies of this skill. Keep actual
results outside the portable resources; private endpoint/profile bindings live
once in the ignored `local.md` beside this file.

## Local installation

For Codex user scope, use `~/.agents/skills/dev-flow`; project scope is
`.agents/skills/dev-flow`. Symlinked skill folders are supported by
[official OpenAI skill documentation](https://learn.chatgpt.com/docs/build-skills).
If this machine already discovers a legacy `~/.codex/skills/dev-flow` link,
keep that installed entry pointed at this same source rather than creating
another independent copy or an unnecessary duplicate discovery entry.

For a Hermes coordinator profile, link its `skills/dev-flow` to this folder
and its `SOUL.md` to `assets/hermes-coordinator.md`. Use a dedicated profile
rather than cloning credentials or changing existing Hermes defaults. Follow
[hermes-coordinator.md](hermes-coordinator.md); Claude profiles remain selectable
for each task. Installed CLI support and a real delegation need separate probes.

For Claude Code terminal sessions, link `~/.claude/skills/dev-flow` or the
intended profile's skills directory to this source. Existing profile directories
that share the main skills directory inherit its link. These paths do not
install the skill into Cowork/cloud sessions. See
[Claude Code skills](https://code.claude.com/docs/en/skills).

From the tools repo root, this example refuses an occupied target, including
a dangling symlink. Select only the desired discovery location:

```bash
(
  skill_source="$(pwd -P)/skills/dev-flow"
  skill_target="$HOME/.agents/skills/dev-flow"
  test -f "$skill_source/SKILL.md" || exit 1
  if test -e "$skill_target" || test -L "$skill_target"; then
    printf '%s\n' "Target exists; inspect and reconcile it before migration." >&2
    exit 1
  fi
  mkdir -p "$(dirname "$skill_target")" || exit 1
  ln -s "$skill_source" "$skill_target"
)
```

Keep links pointed at a retained checkout, never a disposable task worktree.
Do not use copies for local installation. Edit the canonical files here and
validate once; all linked installations see the same content.

### Migrate an existing copy

Inventory active paths and profile indirection before replacing anything.
Compare every differing file and preserve unique approved changes. Keep the
current portable workflow and fresh-bootstrap policy; historical setup content
must not silently restore superseded rules. Move private host setup to this
source's `local.md`, retaining its contents and protecting it with the root
`/local.md` ignore rule. Use `local.example.md` for another host, never copy
someone else's account or machine bindings.

Before retiring a source directory, retain recovery data outside all skill
search paths, verify the canonical files and local setup, then replace the old
source and installed entrypoints with links. Replace only inspected paths;
preserve unrelated profile/configuration files. Confirm every active link and
its references resolve to the same canonical directory without loops.

Recovery archives are historical backups, not another maintained source.
The tools repo's old `docs/skills/dev-flow.md` and
`docs/scripts/validate_dev_flow.md` paths are compatibility links to this
folder's `installation.md` and `validation.md` respectively.

### Private setup and discovery

Read `local.md` only as host-specific bindings and recorded results, subject to
the user's current authority. Keep credentials in their existing credential
store; host setup may reference them but should not contain secret values.
Private `local.md` and optional `local.hermes.yaml` are ignored and excluded from
portable checks/export. Never export an installed folder wholesale: distribute
only portable resources, excluding both files, all `__pycache__` directories
and `.pyc`/`.pyo` bytecode. Bytecode can embed machine paths; runtime caches are
ignored by validation, so a successful check does not certify export contents.
Static package validation is not a staged-secret audit.

Confirm the installed references, then verify discovery in a fresh target
session when available. Invoke `$dev-flow` in Codex or `/dev-flow` in Claude
Code and check the source loaded. If a running session still shows cached
instructions, reload it. Filesystem resolution and fresh-session discovery are
separate checks. No installation action grants commits, pushes, model calls,
account changes or other workflow actions.

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
internal symlinks, the declared private-file ignore rule and known machine/account
binding patterns. Installation-directory symlinks resolve to this source; only
the root regular `local.md` and `local.hermes.yaml` files are omitted from portable content checks. It returns 1
on a violation and 0 on success. It does not install hooks, parse every YAML
feature, validate Markdown anchors, scan arbitrary credential formats or check
remote links. Audit the staged diff for secrets separately. It neither needs
nor contacts Beads, models or external services.

The tests copy portable resources, excluding private `local.md`, to temporary
locations and demonstrate valid
packages passing and missing assets, external dependencies, machine bindings
and incorrect metadata failing. They also check linked installation roots,
private-file scope and rejection of a missing private ignore rule. Installation commands should also be exercised
with temporary destinations, including existing and dangling-link cases,
before changing them. See [validation.md](validation.md). If registering this command as a commit/CI gate later,
follow `deterministic-gates.md` and test that actual trigger and input scope.

Update the entrypoint and its owning references together; keep the contract
template unique and preserve repo-specific choices in generated guides. Review
behavior with realistic scenarios when instructions change. Package checks
and isolated probes do not prove a complete workflow run, target-harness
loading, live hook/CI enforcement or quality gains from multiple models.
