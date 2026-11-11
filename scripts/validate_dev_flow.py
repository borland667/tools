#!/usr/bin/env python3
"""Validate the dev-flow distribution without installed agents or services."""

import argparse
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


REQUIRED_FILES = (
    "SKILL.md",
    "repo-contract.md",
    "engineering-practices.md",
    "test-first.md",
    "review-agents.md",
    "local-second-opinions.md",
    "deterministic-gates.md",
    "evidence-and-learning.md",
    "bootstrap-agents.md",
    "assets/AGENTS.md.template",
    "LICENSE",
    "installation.md",
    "validation.md",
    "local.example.md",
    ".gitignore",
)
PRIVATE_BINDING = re.compile(
    r"/Users/[^/\s]+|/home/[^/\s]+|[A-Za-z]:\\Users\\[^\\\s]+"
    r"|claude-(?:work|personal|local)\b"
)
LOCAL_LINK = re.compile(r"\]\(([^)\n]+)\)")


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


def validate(skill_dir: Path) -> list[str]:
    """Return diagnostics, leaving the package and configuration untouched."""
    root = skill_dir.resolve()
    errors = []
    for name in REQUIRED_FILES:
        if not (root / name).is_file():
            errors.append(f"missing required file: {name}")
    if not root.is_dir():
        return errors

    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_symlink():
            errors.append(f"{relative}: package must contain files, not symlinks")
            continue
        if relative == Path("local.md"):
            if not path.is_file():
                errors.append("local.md: private host setup must be a regular file")
            continue
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            errors.append(f"{relative}: cannot read UTF-8 package resource")
            continue
        if relative == Path(".gitignore") and "/local.md" not in content.splitlines():
            errors.append(".gitignore: must ignore /local.md private host setup")
        if PRIVATE_BINDING.search(content):
            errors.append(f"{relative}: contains a machine/account binding")
        if path.name == "SKILL.md":
            frontmatter = re.match(r"\A---\n(.*?)\n---(?:\n|$)", content, re.S)
            if not frontmatter:
                errors.append("SKILL.md: missing frontmatter")
            else:
                header = frontmatter.group(1)
                if not re.search(r"^name: dev-flow$", header, re.M):
                    errors.append("SKILL.md: expected name: dev-flow")
                if not has_description(header):
                    errors.append("SKILL.md: missing or empty description")
        if path.suffix != ".md" and path.name != "AGENTS.md.template":
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
        "--skill-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "skills" / "dev-flow",
        help="package directory; defaults to this checkout's skills/dev-flow",
    )
    args = parser.parse_args()
    errors = validate(args.skill_dir)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("dev-flow package valid: required files, metadata, local links and portability")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
