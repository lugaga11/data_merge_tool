from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_merge_tool.origin_client import OriginWorkerClient
from data_merge_tool.origin_protocol import OriginWorkerError


FAKE_WORKER = r'''
from __future__ import annotations

import json
import sys
import time


mode = sys.argv[1]

if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="strict")

line = sys.stdin.readline()
if mode == "exit":
    raise SystemExit(3)
if not line:
    raise SystemExit(0)

request = json.loads(line)
request_id = request.get("id")

if mode == "sleep":
    time.sleep(10)
elif mode == "bad_json":
    sys.stdout.write("{not-json}\n")
    sys.stdout.flush()
elif mode == "id_mismatch":
    json.dump({"id": request_id + 100, "ok": True, "result": {"status": "wrong"}}, sys.stdout, ensure_ascii=True)
    sys.stdout.write("\n")
    sys.stdout.flush()
elif mode == "unicode_error":
    json.dump(
        {
            "id": request_id,
            "ok": False,
            "error": {"type": "OriginAutomationError", "message": "未知 Origin worker 命令：绘图失败"},
        },
        sys.stdout,
        ensure_ascii=True,
    )
    sys.stdout.write("\n")
    sys.stdout.flush()
elif mode == "ok":
    json.dump({"id": request_id, "ok": True, "result": {"status": "ok"}}, sys.stdout, ensure_ascii=True)
    sys.stdout.write("\n")
    sys.stdout.flush()
else:
    raise SystemExit(2)
'''


class FakeWorkerClient(OriginWorkerClient):
    def __init__(self, worker_script: Path, mode: str) -> None:
        super().__init__()
        self.worker_script = worker_script
        self.mode = mode

    def _command(self) -> list[str]:
        return [sys.executable, "-B", str(self.worker_script), self.mode]


class OriginWorkerClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.worker_script = Path(self.temp_dir.name) / "fake_origin_worker.py"
        self.worker_script.write_text(textwrap.dedent(FAKE_WORKER), encoding="utf-8")
        self.client: FakeWorkerClient | None = None

    def tearDown(self) -> None:
        if self.client is not None:
            self.client._kill_process()
        self.temp_dir.cleanup()

    def make_client(self, mode: str) -> FakeWorkerClient:
        self.client = FakeWorkerClient(self.worker_script, mode)
        return self.client

    def test_unicode_worker_error_is_preserved(self) -> None:
        client = self.make_client("unicode_error")

        with self.assertRaises(OriginWorkerError) as raised:
            client.request("plot_active_sheet")

        self.assertEqual(str(raised.exception), "未知 Origin worker 命令：绘图失败")
        self.assertNotIn("\ufffd", str(raised.exception))

    def test_malformed_json_resets_worker(self) -> None:
        client = self.make_client("bad_json")

        with self.assertRaisesRegex(OriginWorkerError, "无效响应"):
            client.request("ping")

        self.assertIsNone(client._process)

    def test_response_id_mismatch_resets_worker(self) -> None:
        client = self.make_client("id_mismatch")

        with self.assertRaisesRegex(OriginWorkerError, "响应序号不匹配"):
            client.request("ping")

        self.assertIsNone(client._process)

    def test_worker_exit_resets_and_next_request_restarts(self) -> None:
        client = self.make_client("exit")

        with self.assertRaisesRegex(OriginWorkerError, "已退出"):
            client.request("ping")

        self.assertIsNone(client._process)
        client.mode = "ok"
        self.assertEqual(client.ping(), {"status": "ok"})

    def test_timeout_kills_worker_and_next_request_restarts(self) -> None:
        client = self.make_client("sleep")

        with self.assertRaisesRegex(OriginWorkerError, "响应超时"):
            client.request("ping", timeout_seconds=0.2)

        self.assertIsNone(client._process)
        client.mode = "ok"
        self.assertEqual(client.ping(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
