import unittest
from types import SimpleNamespace

from core.llm.completion_limits import chat_extra_body_for_llm, max_chat_completion_n


class DeepseekModel:
    pass


class QwenModel:
    pass


class CompletionLimitsTests(unittest.TestCase):
    def test_deepseek_class_forces_n_equals_one(self):
        llm = DeepseekModel()
        self.assertEqual(max_chat_completion_n(llm), 1)
        self.assertIsNone(chat_extra_body_for_llm(llm))

    def test_deepseek_base_url_forces_n_equals_one(self):
        llm = SimpleNamespace(client=SimpleNamespace(base_url="https://api.deepseek.com"))
        self.assertEqual(max_chat_completion_n(llm), 1)

    def test_qwen_allows_chunk_of_four_and_thinking_flag(self):
        llm = QwenModel()
        llm.client = SimpleNamespace(base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.assertEqual(max_chat_completion_n(llm), 4)
        self.assertEqual(chat_extra_body_for_llm(llm), {"enable_thinking": False})


if __name__ == "__main__":
    unittest.main()
