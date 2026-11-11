# Validate the dev-flow skill package

`scripts/validate_dev_flow.py` is the offline package gate for
`skills/dev-flow/`. It requires Python 3.9+ with no third-party dependencies.
It validates distribution resources and links without loading a model, using
Beads or changing files. It is not a project-code test or credential scanner.

```bash
python3 scripts/validate_dev_flow.py --help
python3 scripts/validate_dev_flow.py
python3 scripts/validate_dev_flow.py --skill-dir /path/to/copied/dev-flow
```

`--skill-dir` selects the skill folder. By default the script finds the bundle
beside its own checkout, independent of the calling directory. A valid package
prints one success line and exits 0. Violations print resource-specific
diagnostics and exit 1. Invalid CLI arguments exit 2. Diagnostics for private
bindings identify the resource without echoing the matched content.

Quick validation:

```bash
python3 scripts/validate_dev_flow.py
python3 -B -m unittest discover -s tests/dev_flow -v
```

See [the skill package guide](../skills/dev-flow.md) for installation, check
scope and limitations. The command is manual; this change does not install a
Git hook or claim CI enforcement.
