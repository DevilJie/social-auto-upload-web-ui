import json
import sys
import unittest
from pathlib import Path
from queue import Queue
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


class TestLoginSseStream(unittest.TestCase):
    def test_terminal_error_message_closes_stream(self):
        import app as app_module

        status_queue = Queue()
        payload = json.dumps({"status": "error", "msg": "user closed browser"})
        status_queue.put(payload)

        stream = app_module.sse_stream(status_queue)

        self.assertEqual(next(stream), f"data: {payload}\n\n")
        with patch.object(app_module.time, "sleep", side_effect=AssertionError("stream kept waiting")):
            with self.assertRaises(StopIteration):
                next(stream)


if __name__ == "__main__":
    unittest.main()
