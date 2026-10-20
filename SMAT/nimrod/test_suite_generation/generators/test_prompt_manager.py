import unittest

from nimrod.test_suite_generation.generators.prompt_manager import PromptManager


class PromptManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = PromptManager()
        self.method_info = {
            "method_name": "apply(int price)",
            "method_code": "public int apply(int price) {\n    return price;\n}",
            "class_fields": ["public int discount = 0;"],
            "constructor_codes": ["public DiscountCalculator(int discount) { this.discount = discount; }"],
            "left_changes_summary": "Left adds a conditional discount.",
            "right_changes_summary": "Right changes the initial discount.",
        }

    def _combinations(self, template: str):
        return self.manager.generate_all_combinations(
            self.method_info, "DiscountCalculator", "left", template
        )

    def test_generates_eight_zero_shot_combinations(self) -> None:
        combinations = self._combinations("zero_shot")

        self.assertEqual(list(combinations.keys()), [f"prompt{i}" for i in range(1, 9)])
        self.assertEqual(len(combinations["prompt1"]), 3)
        self.assertEqual(len(combinations["prompt8"]), 6)

    def test_zero_shot_prompt2_contains_change_summaries(self) -> None:
        messages = self._combinations("zero_shot")["prompt2"]
        joined = "\n".join(message["content"] for message in messages)

        self.assertIn("Left adds a conditional discount.", joined)
        self.assertIn("Right changes the initial discount.", joined)

    def test_generates_eight_one_shot_combinations_with_example(self) -> None:
        combinations = self._combinations("one_shot")

        self.assertEqual(list(combinations.keys()), [f"prompt{i}" for i in range(1, 9)])
        prompt1 = combinations["prompt1"]
        self.assertEqual(prompt1[0]["role"], "system")
        self.assertTrue(any(message["role"] == "assistant" for message in prompt1))
        self.assertTrue(any("DFPBaseSample" in message["content"] for message in prompt1))
        self.assertEqual(len(combinations["prompt8"]), 12)

    def test_unknown_template_returns_no_combinations(self) -> None:
        self.assertEqual(self._combinations("unknown"), {})

    def test_filters_prompt_keys(self) -> None:
        combinations = self.manager.generate_all_combinations(
            self.method_info,
            "DiscountCalculator",
            "left",
            "zero_shot",
            prompt_keys=["prompt1", "prompt3", "prompt5"],
        )

        self.assertEqual(list(combinations.keys()), ["prompt1", "prompt3", "prompt5"])


if __name__ == "__main__":
    unittest.main()
