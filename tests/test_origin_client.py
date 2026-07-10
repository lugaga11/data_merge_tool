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

from data_merge_tool.origin.client import OriginWorkerClient
from data_merge_tool.origin.protocol import OriginWorkerError
from data_merge_tool.origin.worker import dispatch


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
if mode == "release_then_ping":
    while line:
        request = json.loads(line)
        request_id = request.get("id")
        command = request.get("command")
        if command == "release_origin":
            response = {"id": request_id, "ok": True, "result": {"status": "released"}}
        elif command == "ping":
            response = {"id": request_id, "ok": True, "result": {"status": "ok"}}
        elif command == "shutdown":
            response = {"id": request_id, "ok": True, "result": {"status": "bye"}}
        else:
            response = {"id": request_id, "ok": False, "error": {"message": "unknown"}}
        json.dump(response, sys.stdout, ensure_ascii=True)
        sys.stdout.write("\n")
        sys.stdout.flush()
        if command == "shutdown":
            break
        line = sys.stdin.readline()
    raise SystemExit(0)

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
        self.client: OriginWorkerClient | None = None

    def tearDown(self) -> None:
        if self.client is not None:
            self.client._kill_process()
        self.temp_dir.cleanup()

    def make_client(self, mode: str) -> FakeWorkerClient:
        client = FakeWorkerClient(self.worker_script, mode)
        self.client = client
        return client

    def test_source_worker_module_starts_from_relocated_client(self) -> None:
        client = OriginWorkerClient()
        self.client = client

        self.assertEqual(client._command(), [sys.executable, "-m", "data_merge_tool.origin.worker"])
        self.assertEqual(client.ping(), {"status": "ok"})

        client.shutdown()
        self.assertIsNone(client._process)

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

    def test_release_origin_keeps_worker_available(self) -> None:
        client = self.make_client("release_then_ping")

        self.assertEqual(client.ping(), {"status": "ok"})
        client.release_origin()

        self.assertIsNotNone(client._process)
        self.assertEqual(client.ping(), {"status": "ok"})

    def test_timeout_kills_worker_and_next_request_restarts(self) -> None:
        client = self.make_client("sleep")

        with self.assertRaisesRegex(OriginWorkerError, "响应超时"):
            client.request("ping", timeout_seconds=0.2)

        self.assertIsNone(client._process)
        client.mode = "ok"
        self.assertEqual(client.ping(), {"status": "ok"})

    def test_release_origin_dispatch_detaches_without_shutdown(self) -> None:
        class FakeAdapter:
            def __init__(self) -> None:
                self.force: bool | None = None

            def detach(self, force: bool = False) -> None:
                self.force = force

        adapter = FakeAdapter()

        result = dispatch(adapter, "release_origin", {})  # type: ignore[arg-type]

        self.assertEqual(result, {"status": "released"})
        self.assertTrue(adapter.force)


if __name__ == "__main__":
    unittest.main()
