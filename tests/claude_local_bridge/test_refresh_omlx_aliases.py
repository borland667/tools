#!/usr/bin/env python3

import importlib.util
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
HELPER_PATH = ROOT_DIR / "claude_local_bridge" / "refresh_omlx_cowork_models.py"

spec = importlib.util.spec_from_file_location("refresh_omlx_cowork_models", HELPER_PATH)
refresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refresh)


class RefreshOmlxAliasTests(unittest.TestCase):
    def test_generates_unique_claude_aliases_for_all_usable_models(self):
        route_map = refresh.build_route_map(
            [
                {"id": "Qwen3-Next-80B-A3B-Instruct-4bit"},
                {"id": "Qwen3-Next-80B-A3B-Thinking-4bit"},
                {"id": "Qwen3-VL-4B-Instruct-4bit"},
                {"id": "Qwen3.5-9b-Sushi-Coder-RL-MLX"},
                {"id": "Qwen3.6-27B-Heretic-MLX-bf16"},
                {"id": "Qwen3.6-35B-A3B-Claude-Opus-VL-grafted-MLX-8bit"},
                {"id": "Qwen3.6-35B-A3B-MLX-4bit"},
                {"id": "gemma-4-12b-coder-fable5-composer2.5-8bit"},
                {"id": "gemma-4-e4b-it-4bit"},
            ]
        )

        aliases = refresh.build_claude_desktop_models(route_map)
        refresh.validate_claude_desktop_models(aliases, route_map)

        names = [alias["name"] for alias in aliases]
        targets = [alias["target"] for alias in aliases]
        self.assertEqual(len(names), 9)
        self.assertEqual(len(set(names)), 9)
        self.assertEqual(set(targets), set(route_map))
        self.assertIn("claude-sonnet-4-5", names)
        self.assertIn("claude-sonnet-4-6", names)
        self.assertIn("claude-opus-4-5", names)
        self.assertIn("claude-opus-4-8", names)
        self.assertIn("claude-opus-4-1", names)
        self.assertIn("claude-haiku-4-5", names)
        self.assertIn("claude-haiku-4-5-20251001", names)

        defaults_by_tier = {}
        for alias in aliases:
            tier = alias["anthropicFamilyTier"]
            if alias["isFamilyDefault"]:
                defaults_by_tier[tier] = defaults_by_tier.get(tier, 0) + 1
        self.assertTrue(all(count == 1 for count in defaults_by_tier.values()))


if __name__ == "__main__":
    unittest.main()
