# Claude Multi Launcher

## Purpose

`claude_multi_launcher/` documents a macOS pattern for running multiple
isolated Claude Desktop profiles side by side, each with its own launcher and
profile directory.

The folder currently contains a README-style operating note:

```text
/Users/borland/tools/claude_multi_launcher/README.md
```

## Requirements

- macOS.
- Claude Desktop installed at `/Applications/Claude.app`.
- Optional Python 3 plus Pillow if icon recoloring scripts are added.

## Usage

Follow the workflow in the folder README. The core idea is launching Claude
with an Electron user-data directory:

```bash
open -n -a "/Applications/Claude.app" --args --user-data-dir="$HOME/.claude-instances/work"
```

## Output

The documented workflow creates separate Claude profile directories, such as:

```text
$HOME/.claude-instances/work
$HOME/.claude-instances/personal
```

## Safety Notes

Use one profile directory per account. Do not point multiple launchers at the
same Claude profile, because duplicate Electron processes can create logged-out
or inconsistent windows for the same profile.

## Known Limitations

This directory currently contains documentation only. The referenced launcher
helper scripts should be added before treating it as a runnable packaged tool.
