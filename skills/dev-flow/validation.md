# Validate the dev-flow skill package

`scripts/validate_dev_flow.py` is the offline package gate for
`skills/dev-flow/` and its sibling `skills/repo-scaffold/`. It requires Python
3.9+ with no third-party dependencies. It validates distribution resources and
links without loading a model, using Beads or changing files. It is not a
project-code test or credential scanner. It checks required files, skill
frontmatter, links inside Markdown files and templates, and machine or account
bindings in every text file; it does not execute the shell assets or check their
syntax.

```bash
python3 scripts/validate_dev_flow.py --help
python3 scripts/validate_dev_flow.py
python3 scripts/validate_dev_flow.py --skill repo-scaffold
python3 scripts/validate_dev_flow.py --skill-dir /path/to/copied/dev-flow
python3 scripts/validate_dev_flow.py --skill repo-scaffold --skill-dir /path/to/copied/repo-scaffold
```

With no arguments the script checks every package beside its own checkout,
independent of the calling directory. `--skill` picks one package and its
required-file list; `--skill-dir` points at a copied folder and defaults the
package to dev-flow. Each valid package prints one success line; exit 0 means
all checked packages are valid. Violations print resource-specific
diagnostics and exit 1. Invalid CLI arguments exit 2. Diagnostics for private
bindings identify the resource without echoing the matched content.

Quick validation:

```bash
python3 scripts/validate_dev_flow.py
python3 -B -m unittest discover -s tests/dev_flow -v
```

See [installation.md](installation.md) for installation, check
scope and limitations. Root installation symlinks are followed; internal
symlinks are rejected. Only root regular `local.md` and `local.hermes.yaml` are
excluded from portable checks; `.gitignore` must declare both paths. This verifies
the declaration, not Git index state or arbitrary secret formats. Portable test
fixtures exclude both files; nested files with either name remain checked.
Generated `__pycache__` contents and `.pyc`/`.pyo` files are runtime artifacts,
ignored by the package and excluded from portable fixture copies. Internal
symlinks are rejected even inside a cache directory.
The command is manual; this change does not install a
Git hook or claim CI enforcement.
