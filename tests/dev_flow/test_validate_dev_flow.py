"""Exercise the shipped validator against complete and damaged distributions."""

import importlib.util
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "validate_dev_flow.py"
SPEC = importlib.util.spec_from_file_location("validate_dev_flow", SCRIPT)
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class PackageValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dev-flow-package-")
        self.addCleanup(self.temp.cleanup)
        self.package = Path(self.temp.name) / "relocated" / "dev-flow"
        source = REPO / "skills" / "dev-flow"
        shutil.copytree(
            source, self.package,
            ignore=lambda directory, names: [name for name in names
                if name == '__pycache__' or Path(name).suffix in {'.pyc', '.pyo'}
                or (Path(directory) == source and name in VALIDATOR.PRIVATE_LOCAL_FILES)],
        )

    def run_cli(self):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--skill-dir", str(self.package)],
            cwd=self.temp.name,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_relocated_complete_distribution_works_without_checkout_cwd(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_selecting_one_skill_validates_only_that_package(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--skill", "dev-flow"],
            cwd=self.temp.name, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("dev-flow package valid", result.stdout)
        self.assertNotIn("repo-scaffold", result.stdout)

    def test_unknown_skill_selection_exits_two(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--skill", "not-a-package"],
            cwd=self.temp.name, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_missing_required_resources_fail_with_useful_diagnostic(self):
        for name in ["assets/AGENTS.md.template", "engineering-practices.md",
                     "invariant-guards.md", "assets/PR.md.template"]:
            with self.subTest(resource=name):
                path = self.package / name
                original = path.read_bytes()
                path.unlink()
                result = self.run_cli()
                self.assertEqual(result.returncode, 1)
                self.assertIn(name, result.stdout)
                path.write_bytes(original)

    def test_link_to_an_existing_file_outside_bundle_is_rejected(self):
        (self.package.parent / "outside.md").write_text("External content\n")
        guide = self.package / "SKILL.md"
        with guide.open("a") as output:
            output.write("\n[unbundled dependency](../outside.md)\n")
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertIn("link leaves package", result.stdout)

    def test_missing_nonrequired_reference_is_rejected(self):
        with (self.package / "SKILL.md").open("a") as output:
            output.write("\n[missing reference](references/missing.md)\n")
        self.assertTrue(any("missing linked resource" in e for e in VALIDATOR.validate(self.package)))

    def test_symlink_to_machine_resource_is_rejected(self):
        external = self.package.parent / "private.md"
        external.write_text("Private source\n")
        (self.package / "extra.md").symlink_to(external)
        self.assertTrue(any("symlinks" in e for e in VALIDATOR.validate(self.package)))

    def test_root_installation_symlink_resolves_the_canonical_package(self):
        installed = Path(self.temp.name) / "installed-dev-flow"
        installed.symlink_to(self.package, target_is_directory=True)
        self.assertEqual(VALIDATOR.validate(installed), [])

    def test_private_host_bindings_are_allowed_only_in_root_local_file(self):
        (self.package / "local.md").write_text("Host path: /Users/fixture-user/private\n")
        self.assertEqual(VALIDATOR.validate(self.package), [])
        nested = self.package / "references"
        nested.mkdir()
        (nested / "local.md").write_text("Host path: /Users/fixture-user/private\n")
        self.assertTrue(any("machine/account binding" in e for e in VALIDATOR.validate(self.package)))

    def test_private_host_file_cannot_be_a_symlink(self):
        external = self.package.parent / "private-host.md"
        external.write_text("Host path: /Users/fixture-user/private\n")
        (self.package / "local.md").symlink_to(external)
        self.assertTrue(any("symlinks" in e for e in VALIDATOR.validate(self.package)))

    def test_missing_private_ignore_rule_is_rejected(self):
        (self.package / ".gitignore").write_text("# no private host exclusion\n")
        self.assertTrue(any("local.md" in e and "ignore" in e for e in VALIDATOR.validate(self.package)))

    def test_private_hermes_config_is_excluded_but_requires_its_ignore_rule(self):
        config = self.package / 'local.hermes.yaml'
        config.write_text('profile_path: /Users/fixture-user/private\n')
        with (self.package / '.gitignore').open('a') as f:
            f.write('/local.hermes.yaml\n')
        self.assertEqual(VALIDATOR.validate(self.package), [])
        (self.package / '.gitignore').write_text('/local.md\n')
        self.assertTrue(any('local.hermes.yaml' in e and 'ignore' in e for e in VALIDATOR.validate(self.package)))

    def test_unreadable_ignore_encoding_reports_a_diagnostic(self):
        (self.package / ".gitignore").write_bytes(b"\xff")
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot read UTF-8 package resource", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_bytecode_cache_is_not_portable_content_but_symlinks_still_fail(self):
        cache = self.package / 'scripts/__pycache__'
        cache.mkdir(parents=True)
        (cache / 'run_worker.cpython-39.pyc').write_bytes(b'\xff\x00runtime cache')
        self.assertEqual(VALIDATOR.validate(self.package), [])
        external = self.package.parent / 'external.pyc'
        external.write_bytes(b'cache')
        (cache / 'linked.pyc').symlink_to(external)
        self.assertTrue(any('symlinks' in e for e in VALIDATOR.validate(self.package)))

    def test_machine_path_fails_without_echoing_private_content(self):
        private_path = "/Users/fixture-user/private/config"
        with (self.package / "review-agents.md").open("a") as output:
            output.write("\nUse " + private_path + "\n")
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertIn("machine/account binding", result.stdout)
        self.assertNotIn(private_path, result.stdout + result.stderr)

    def test_wrong_skill_identity_is_rejected(self):
        path = self.package / "SKILL.md"
        path.write_text(path.read_text().replace("name: dev-flow", "name: other-skill", 1))
        self.assertTrue(any("expected name" in e for e in VALIDATOR.validate(self.package)))

    def test_empty_descriptions_fail_discovery_metadata_gate(self):
        path = self.package / "SKILL.md"
        for header in [
            "name: dev-flow\ndescription: >-",
            "description:\nname: dev-flow",
            'name: dev-flow\ndescription: ""',
            "name: dev-flow\ndescription: '   '",
        ]:
            with self.subTest(header=header):
                path.write_text("---\n" + header + "\n---\n# Dev flow\n")
                result = self.run_cli()
                self.assertEqual(result.returncode, 1)
                self.assertIn("empty description", result.stdout)


class RepoScaffoldValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="repo-scaffold-package-")
        self.addCleanup(self.temp.cleanup)
        self.package = Path(self.temp.name) / "relocated" / "repo-scaffold"
        source = REPO / "skills" / "repo-scaffold"
        shutil.copytree(source, self.package, ignore=lambda directory, names: [
            name for name in names if Path(directory) == source and name == "local.md"])

    def run_cli(self, *extra):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--skill", "repo-scaffold",
             "--skill-dir", str(self.package), *extra],
            cwd=self.temp.name, capture_output=True, text=True, check=False,
        )

    def test_relocated_complete_package_is_valid(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("repo-scaffold package valid", result.stdout)

    def test_missing_required_resource_fails(self):
        (self.package / "assets" / "worktree-ports.sh").unlink()
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertIn("assets/worktree-ports.sh", result.stdout)

    def test_dev_flow_identity_is_rejected_for_this_package(self):
        path = self.package / "SKILL.md"
        path.write_text(path.read_text().replace("name: repo-scaffold", "name: dev-flow", 1))
        self.assertTrue(any("expected name: repo-scaffold" in e
                            for e in VALIDATOR.validate(self.package, "repo-scaffold")))

    def test_broken_link_in_a_markdown_template_is_rejected(self):
        with (self.package / "assets" / "decision.md.template").open("a") as output:
            output.write("\n[gone](missing.md)\n")
        self.assertTrue(any("missing linked resource" in e
                            for e in VALIDATOR.validate(self.package, "repo-scaffold")))

    def test_machine_path_in_a_script_asset_is_rejected(self):
        with (self.package / "assets" / "bootstrap.sh.template").open("a") as output:
            output.write("\n# /Users/fixture-user/private\n")
        self.assertTrue(any("machine/account binding" in e
                            for e in VALIDATOR.validate(self.package, "repo-scaffold")))

    def test_no_arguments_validates_every_package_in_the_checkout(self):
        result = subprocess.run([sys.executable, str(SCRIPT)], cwd=self.temp.name,
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("dev-flow package valid", result.stdout)
        self.assertIn("repo-scaffold package valid", result.stdout)

    def test_missing_private_ignore_rule_is_rejected(self):
        path = self.package / ".gitignore"
        path.write_text(path.read_text().replace("/local.md\n", ""))
        self.assertTrue(any("must ignore /local.md" in e
                            for e in VALIDATOR.validate(self.package, "repo-scaffold")))

    def test_no_arguments_names_a_failing_package(self):
        checkout = Path(self.temp.name) / "checkout"
        shutil.copytree(REPO / "scripts", checkout / "scripts")
        shutil.copytree(REPO / "skills", checkout / "skills",
                        ignore=lambda directory, names: [
                            name for name in names
                            if name == "__pycache__" or Path(name).suffix in {".pyc", ".pyo"}])
        (checkout / "skills" / "repo-scaffold" / "checklist.md").unlink()
        result = subprocess.run(
            [sys.executable, str(checkout / "scripts" / "validate_dev_flow.py")],
            cwd=self.temp.name, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("ERROR: repo-scaffold: missing required file: checklist.md",
                     result.stdout)
        self.assertIn("dev-flow package valid", result.stdout)


class ScaffoldScriptTests(unittest.TestCase):
    """Behaviour of the shipped shell assets, not just their presence."""

    ASSETS = REPO / "skills" / "repo-scaffold" / "assets"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="scaffold-scripts-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def git(self, repo, *args):
        return subprocess.run(["git", "-C", str(repo), *args],
                              capture_output=True, text=True, check=True)

    def new_repo(self):
        repo = self.root / "repo"
        repo.mkdir()
        self.git(repo, "init", "-q")
        self.git(repo, "config", "user.email", "test@example.com")
        (repo / "README.md").write_text("example\n")
        self.git(repo, "add", "README.md")
        self.git(repo, "commit", "-qm", "init")
        return repo

    def source_in(self, script, directory):
        """Source the script in a child shell and print the resolved values."""
        runner = self.root / "source-report.sh"
        runner.write_text('. "$SRC"\nprintf "%s|%s|%s\\n" '
                          '"$WORKTREE_SLOT" "$WEB_PORT" "$COMPOSE_PROJECT_NAME"\n')
        return subprocess.run(
            ["bash", str(runner)], cwd=str(directory),
            env={**os.environ, "SRC": str(script)},
            capture_output=True, text=True, check=False,
        )

    def test_shell_assets_parse(self):
        for name in ("worktree-ports.sh", "bootstrap.sh.template"):
            result = subprocess.run(["bash", "-n", str(self.ASSETS / name)],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_worktrees_get_distinct_stable_slots(self):
        repo = self.new_repo()
        first = self.root / "wt-a"
        second = self.root / "wt-b"
        self.git(repo, "worktree", "add", "-q", str(first), "-b", "wt-a")
        self.git(repo, "worktree", "add", "-q", str(second), "-b", "wt-b")
        script = self.ASSETS / "worktree-ports.sh"

        main = self.source_in(script, repo)
        again = self.source_in(script, first)
        other = self.source_in(script, second)
        self.assertEqual(again.stdout, self.source_in(script, first).stdout)
        slot_a, port_a, compose_a = again.stdout.strip().split("|")
        slot_b, port_b, compose_b = other.stdout.strip().split("|")
        self.assertEqual(main.stdout.strip().split("|")[0], "0")
        self.assertEqual(len(again.stdout.strip().splitlines()), 1, again.stdout)
        self.assertNotEqual(slot_a, slot_b)
        self.assertEqual(int(port_a), 3000 + 10 * int(slot_a))
        self.assertEqual(int(port_b), 3000 + 10 * int(slot_b))
        self.assertNotEqual(compose_a, compose_b)
        self.assertTrue(compose_b.islower())

    def test_removed_worktree_frees_its_slot(self):
        repo = self.new_repo()
        first = self.root / "wt-a"
        self.git(repo, "worktree", "add", "-q", str(first), "-b", "wt-a")
        script = self.ASSETS / "worktree-ports.sh"
        slot = self.source_in(script, first).stdout.strip().split("|")[0]
        self.git(repo, "worktree", "remove", "--force", str(first))
        freed = self.root / "wt-b"
        self.git(repo, "worktree", "add", "-q", str(freed), "-b", "wt-b")
        self.assertEqual(self.source_in(script, freed).stdout.strip().split("|")[0], slot)

    def test_exhausted_slots_leave_ports_unset(self):
        repo = self.new_repo()
        limited = self.root / "limited.sh"
        limited.write_text((self.ASSETS / "worktree-ports.sh").read_text()
                           .replace("_wt_max_slots=50", "_wt_max_slots=1"))
        first = self.root / "wt-a"
        second = self.root / "wt-b"
        self.git(repo, "worktree", "add", "-q", str(first), "-b", "wt-a")
        self.git(repo, "worktree", "add", "-q", str(second), "-b", "wt-b")
        self.assertEqual(self.source_in(limited, first).stdout.strip().split("|")[0], "1")
        result = self.source_in(limited, second)
        self.assertEqual(result.stdout.strip(), "||", result.stdout)
        self.assertIn("all 1 slots are claimed", result.stderr)

    def test_executing_prints_and_sourcing_does_not(self):
        repo = self.new_repo()
        worktree = self.root / "wt-a"
        self.git(repo, "worktree", "add", "-q", str(worktree), "-b", "wt-a")
        executed = subprocess.run(["bash", str(self.ASSETS / "worktree-ports.sh")],
                                  cwd=str(worktree), capture_output=True, text=True, check=False)
        self.assertIn("COMPOSE_PROJECT_NAME=", executed.stdout)
        sourced = subprocess.run(["bash", "-c", 'set -- info; . "$SRC"; printf ok'],
                                 cwd=str(worktree), env={**os.environ,
                                                        "SRC": str(self.ASSETS / "worktree-ports.sh")},
                                 capture_output=True, text=True, check=False)
        self.assertEqual(sourced.stdout, "ok", sourced.stdout + sourced.stderr)

    def test_bootstrap_rejects_unknown_flags(self):
        filled = self.root / "bootstrap.sh"
        filled.write_text((self.ASSETS / "bootstrap.sh.template").read_text()
                          .replace("{{FIELD}}", "TOOL"))
        result = subprocess.run(["bash", str(filled), "--dry-run"],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("usage:", result.stderr)


if __name__ == "__main__":
    unittest.main()
