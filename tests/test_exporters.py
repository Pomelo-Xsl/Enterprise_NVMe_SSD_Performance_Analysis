import unittest
from exporters import samples_csv, task_json

class ExportTests(unittest.TestCase):
    def test_csv_has_headers_and_values(self):
        text = samples_csv([{"minute": 1, "bandwidth": 100, "iops": 5, "latency": 9, "temperature": 40}])
        self.assertIn("bandwidth", text)
        self.assertIn("100", text)

    def test_json_preserves_chinese(self):
        self.assertIn("测试", task_json({"name": "测试"}))

if __name__ == "__main__": unittest.main()
