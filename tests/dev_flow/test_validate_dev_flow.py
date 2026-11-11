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
        shutil.copytree(REPO / "skills" / "dev-flow", self.package)

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
