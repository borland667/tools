#!/usr/bin/env python3
"""Validate the dev-flow and repo-scaffold skill packages without installed agents or services."""

import argparse
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


REQUIRED_FILES = (
    "SKILL.md",
    "repo-contract.md",
    "ticket-mapping.md",
    "engineering-practices.md",
    "task-intake.md",
    "design-decisions.md",
    "acceptance-exercise.md",
    "test-first.md",
    "review-agents.md",
    "model-selection.md",
    "local-second-opinions.md",
    "hermes-coordinator.md",
    "worker-launcher.md",
    "scripts/run_worker.py",
    "assets/hermes-coordinator.md",
    "deterministic-gates.md",
    "evidence-and-learning.md",
    "tmp-docs.md",
    "assets/TMP.md.template",
    "bootstrap-agents.md",
    "assets/AGENTS.md.template",
    "LICENSE",
    "installation.md",
    "validation.md",
    "local.example.md",
    "invariant-guards.md",
    "assets/PR.md.template",
    ".gitignore",
)
REPO_SCAFFOLD_REQUIRED_FILES = (
    "SKILL.md",
    "practices.md",
    "layout.md",
    "delivery.md",
    "checklist.md",
    "assets/ARCHITECTURE.md.template",
    "assets/decision.md.template",
    "assets/runbook.md.template",
    "assets/CLEAN-BUILDS.md.template",
    "assets/bootstrap.sh.template",
    "assets/worktree-ports.sh",
    "LICENSE",
    ".gitignore",
)
PRIVATE_BINDING = re.compile(
    r"/Users/[^/\s]+|/home/[^/\s]+|[A-Za-z]:\\Users\\[^\\\s]+"
    r"|claude-(?:work|personal|local)\b"
)
LOCAL_LINK = re.compile(r"\]\(([^)\n]+)\)")
PRIVATE_LOCAL_FILES = frozenset({"local.md", "local.hermes.yaml"})
PACKAGES = {
    "dev-flow": (REQUIRED_FILES, PRIVATE_LOCAL_FILES),
    "repo-scaffold": (REPO_SCAFFOLD_REQUIRED_FILES, frozenset({"local.md"})),
}


def has_description(header: str) -> bool:
    lines = header.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("description:"):
            continue
        value = line.partition(":")[2].strip()
        if value in {">", ">-", ">+", "|", "|-", "|+"}:
            for following in lines[index + 1:]:
                if not following.strip():
                    continue
                return following.startswith((" ", "\t"))
            return False
        return bool(value.strip("\"'").strip())
    return False


def validate(skill_dir: Path, package: str = "dev-flow") -> list[str]:
    """Return diagnostics, leaving the package and configuration untouched."""
    required, private_files = PACKAGES[package]
    root = skill_dir.resolve()
    errors = []
    for name in required:
        if not (root / name).is_file():
            errors.append(f"missing required file: {name}")
    if not root.is_dir():
        return errors

    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_symlink():
            errors.append(f"{relative}: package must contain files, not symlinks")
            continue
        if str(relative) in private_files:
            if not path.is_file():
                errors.append(f"{relative}: private host setup must be a regular file")
            continue
        if not path.is_file():
            continue
        if '__pycache__' in relative.parts or path.suffix in {'.pyc', '.pyo'}:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            errors.append(f"{relative}: cannot read UTF-8 package resource")
            continue
        if relative == Path(".gitignore"):
            for private in sorted(private_files):
                if "/" + private not in content.splitlines():
                    errors.append(f".gitignore: must ignore /{private} private host setup")
        if PRIVATE_BINDING.search(content):
            errors.append(f"{relative}: contains a machine/account binding")
        if path.name == "SKILL.md":
            frontmatter = re.match(r"\A---\n(.*?)\n---(?:\n|$)", content, re.S)
            if not frontmatter:
                errors.append("SKILL.md: missing frontmatter")
            else:
                header = frontmatter.group(1)
                if not re.search(rf"^name: {re.escape(package)}$", header, re.M):
                    errors.append(f"SKILL.md: expected name: {package}")
                if not has_description(header):
                    errors.append("SKILL.md: missing or empty description")
        if path.suffix != ".md" and not path.name.endswith(".md.template"):
            continue
        for target in LOCAL_LINK.findall(content):
            target = target.strip().removeprefix("<").removesuffix(">")
            url = urlsplit(target)
            if url.scheme in {"https", "http", "mailto"}:
                continue
            if url.scheme or url.netloc:
                errors.append(f"{relative}: nonportable link: {target}")
                continue
            linked = (path.parent / unquote(url.path)).resolve()
            if not linked.is_relative_to(root):
                errors.append(f"{relative}: link leaves package: {target}")
            elif not linked.exists():
                errors.append(f"{relative}: missing linked resource: {target}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skill",
        choices=sorted(PACKAGES),
        help="package to validate; defaults to dev-flow with --skill-dir, "
             "otherwise every package in this checkout",
    )
    parser.add_argument(
        "--skill-dir",
        type=Path,
        help="package directory; defaults to this checkout's skills/<skill>",
    )
    args = parser.parse_args()
    skills_root = Path(__file__).resolve().parents[1] / "skills"
    if args.skill_dir is not None:
        targets = [(args.skill or "dev-flow", args.skill_dir)]
    else:
        names = [args.skill] if args.skill else sorted(PACKAGES)
        targets = [(name, skills_root / name) for name in names]
    failed = False
    for package, skill_dir in targets:
        errors = validate(skill_dir, package)
        for error in errors:
            print(f"ERROR: {package}: {error}" if len(targets) > 1 else f"ERROR: {error}")
        if errors:
            failed = True
        else:
            print(f"{package} package valid: required files, metadata, local links and portability")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
