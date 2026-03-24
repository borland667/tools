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
- Do not commit directly to `main`/`master`.

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
