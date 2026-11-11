"""Exercise the shipped validator against complete and damaged distributions."""

import importlib.util
from pathlib import Path
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

    def test_missing_required_resources_fail_with_useful_diagnostic(self):
        for name in ["assets/AGENTS.md.template", "engineering-practices.md"]:
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


if __name__ == "__main__":
    unittest.main()
