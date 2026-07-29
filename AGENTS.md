# AGENTS.md

Agent operating guidance for this repository.

## Scope

This repository is a personal collection of scripts/tools. It currently includes
`media_carver.py` and may grow over time.

## Repository-Level Standards

- Repository is mixed-language; choose language per script purpose.
- Prefer small, focused scripts with explicit inputs and outputs.
- Keep changes scoped and avoid bundling unrelated modifications.
- Use safe defaults; require explicit flags for risky operations.

## Core Working Rules

- Keep changes minimal and targeted; do one thing at a time.
- Preserve existing behavior unless fixing a verified bug.
- Prefer the simplest implementation that satisfies requirements.
- Never perform destructive operations against source media in recovery flows.
- Committing directly to `main` is allowed in this repository.
- Once a requested task is completed and validated, commit the completed
  changes unless the user explicitly asks not to commit.
- Before committing or pushing, audit the staged/tracked changes for secrets
  and credentials. Do not commit real API keys, tokens, passwords, private
  keys, `.env` files, or machine-local credentials. Placeholders such as
  `sk-local`, `lmstudio`, `replace-with-...`, and values in `.env.example`
  files are acceptable only when clearly non-secret.

## Documentation Requirements

When modifying this repository:

- Always assess whether `README.md` should be updated.
- Keep `README.md` conventions-first and keep script index current.
- Maintain one dedicated doc per script under `docs/scripts/`.
- If script behavior, flags, output structure, or requirements change, update
  docs in the same change.
- Prefer updating existing docs over creating redundant new documents.

## Media Carver-Specific Guidance

### Safety and Forensics Posture

- Treat input devices/images as read-only sources.
- Avoid suggestions that write back to source block devices.
- Favor workflows that clone evidence and operate on the clone.

### Behavioral Expectations

- Keep persistent state semantics stable unless explicitly requested:
  - `.scan_state/seen_hashes.txt`
  - `.scan_state/counters.json`
  - `.scan_state/scan_log.txt`
- Preserve deterministic output naming conventions unless requested to change.
- Maintain scan boundary protections (buffer overlap/chunk overlap).

### Validation and Recovery Logic

- Be cautious changing end-of-file detection strategies; these are format-
  specific heuristics and regressions can silently reduce recovery quality.
- Keep JPEG validation tolerant when Pillow is unavailable.
- If adding formats, document:
  - signature bytes and offsets,
  - end-finding strategy,
  - expected min/max size behavior.

## Testing Guidance

No formal test suite exists yet. For substantive changes:

- Run the script's `--help` output for CLI sanity.
- Perform a small range scan against a known sample image/device dump when
  available.
- Verify report output and state file updates.

## Style Guidance

- Keep scripts straightforward and dependency-light.
- Use clear names and short functions where practical.
- Add comments only where logic is non-obvious.
- Follow language-appropriate conventions (shellcheck for shell, lint/format
  where available for Python/JS/etc.).

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:970c3bf2 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Agent Context Profiles

The managed Beads block is task-tracking guidance, not permission to override repository, user, or orchestrator instructions.

- **Conservative (default)**: Use `bd` for task tracking. Do not run git commits, git pushes, or Dolt remote sync unless explicitly asked. At handoff, report changed files, validation, and suggested next commands.
- **Minimal**: Keep tool instruction files as pointers to `bd prime`; use the same conservative git policy unless active instructions say otherwise.
- **Team-maintainer**: Only when the repository explicitly opts in, agents may close beads, run quality gates, commit, and push as part of session close. A current "do not commit" or "do not push" instruction still wins.

## Session Completion

This protocol applies when ending a Beads implementation workflow. It is subordinate to explicit user, repository, and orchestrator instructions.

1. **File issues for remaining work** - Create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Handle git/sync by active profile**:
   ```bash
   # Conservative/minimal/default: report status and proposed commands; wait for approval.
   git status

   # Team-maintainer opt-in only, unless current instructions forbid it:
   git pull --rebase
   bd dolt push
   git push
   git status
   ```
5. **Hand off** - Summarize changes, validation, issue status, and any blocked sync/commit/push step

**Critical rules:**
- Explicit user or orchestrator instructions override this Beads block.
- Do not commit or push without clear authority from the active profile or the current user request.
- If a required sync or push is blocked, stop and report the exact command and error.
<!-- END BEADS INTEGRATION -->

<!-- BEGIN BEADS CODEX SETUP: generated by bd setup codex -->
## Beads Issue Tracker

Use Beads (`bd`) for durable task tracking in repositories that include it. Use the `beads` skill at `.agents/skills/beads/SKILL.md` (project install) or `~/.agents/skills/beads/SKILL.md` (global install) for Beads workflow guidance, then use the `bd` CLI for issue operations.

### Quick Reference

```bash
bd ready                # Find available work
bd show <id>            # View issue details
bd update <id> --claim  # Claim work
bd close <id>           # Complete work
bd prime                # Refresh Beads context
```

### Rules

- Use `bd` for all task tracking; do not create markdown TODO lists.
- Run `bd prime` when Beads context is missing or stale. Codex 0.129.0+ can load Beads context automatically through native hooks; use `/hooks` to inspect or toggle them.
- Keep persistent project memory in Beads via `bd remember`; do not create ad hoc memory files.

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.
<!-- END BEADS CODEX SETUP -->
