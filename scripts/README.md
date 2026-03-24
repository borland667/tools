# Scripts Helpers

Helper scripts for repository maintenance and automation.

## `install-to-bin.sh`

Install one or more repository scripts into `~/bin` so they are runnable from
`$PATH`.

By default, installation uses symlinks (recommended), so updates in this repo
are reflected immediately.

### Usage

```bash
scripts/install-to-bin.sh [options] <script-path> [<script-path> ...]
scripts/install-to-bin.sh [options] --all
```

### Options

- `--all`: install all top-level executable scripts from repo root
- `--copy`: copy files to `~/bin` instead of symlinking
- `--force`: replace existing file/link in `~/bin`
- `--dry-run`: print actions without changing files
- `-h`, `--help`: show help

### Examples

Install one script:

```bash
scripts/install-to-bin.sh media_carver.py
```

Install all top-level executable scripts:

```bash
scripts/install-to-bin.sh --all
```

Preview only:

```bash
scripts/install-to-bin.sh --all --dry-run
```

### PATH setup

If `~/bin` is not already in your Bash PATH, add this to `~/.bashrc`:

```bash
export PATH="$HOME/bin:$PATH"
```

Then reload your shell and verify:

```bash
source ~/.bashrc
which media_carver.py
```
