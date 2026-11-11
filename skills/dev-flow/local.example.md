# dev-flow: local setup (example)

Copy to `local.md` in this folder and fill it in. `local.md` is gitignored:
the skill reads this machine's agents, accounts and models from it, and none
of that is committed. Delete sections that do not apply.

## Machine

`<chip, memory, OS version>`

## Claude Code account profiles

| Launcher | Config folder | Account |
|---|---|---|
| `<command>` | `<folder>` | `<which account>` |

`<any profile that must not be used, e.g. an unsigned default>`

Herdr key bindings: `<binding> <profile>`, or none.

## Harnesses

| Harness | Use | Launch | Status |
|---|---|---|---|
| `<agent>` | `<lead / reviewer / local passes>` | `<command>` | `<works / needs sign-in / not tried>` |

Default pairing: `<who leads and builds; who reviews and plans second>`.

Coordinator: `<herdr / hermes / none>` by default; Hermes profile
`<coordinator profile name>` if used.

## Local models

- **Server:** `<server and address>`, or none.
- **Local fast model:** `<model>` or not chosen.
- **Local heavy model:** `<model>` or not chosen, with any memory limits.

## Engine results

| Harness | Model | Role tried | Result |
|---|---|---|---|
| `<harness>` | `<model>` | `<role>` | `<date: what happened>` |

## Verification log

- `<date>: <what was run and what it showed>`

## Known issues

- `<anything an agent should check before trusting a step>`
