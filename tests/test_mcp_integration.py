"""Integration test for PatentAgent MCP server via stdio transport.

Tests the full MCP lifecycle:
  1. initialize → verify server capabilities
  2. tools/list → verify all 24 tools and algorithm evidence descriptions
  3. tools/call → verify get_dataset_summary works
  4. tools/call → verify error handling for unknown tool
"""

import asyncio
import json
import os
import sys
import subprocess
import tempfile
import unittest
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class TestMCPStdioIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.temp_dir = tmp
        cls.mcp_input = tmp.name
        os.makedirs(cls.mcp_input, exist_ok=True)

        sample = """FN Thomson Reuters Web of Science
VR 1.0
PN US20240000001A1
TI  Solid-state battery with improved electrolyte
AE  CONTEMPORARY AMPEREX TECH CO LTD
AU  ZHANG SAN
AB  A solid-state battery includes a cathode, an anode, and a solid
    electrolyte layer with high ionic conductivity.
IP  H01M10/0562; H01M10/0525; H01M4/133
DC  A85; B02; C01
PD  04 Jan 2024
PI  CN 201910123456 05 Jun 2019
CR  US10123456B2 2018

"""

        for i in range(1, 6):
            fname = f"download_ ({i}).txt"
            content = sample.replace("US20240000001A1", f"US2024000000{i}A1").replace(
                "Solid-state battery", f"Patent {i}: battery technology"
            ).replace("ZHANG SAN", f"INVENTOR{i}").replace(
                "CONTEMPORARY AMPEREX TECH CO LTD", f"COMPANY_{i} LTD"
            ).replace("04 Jan 2024", f"0{i} Jan 2024")
            with open(os.path.join(cls.mcp_input, fname), "w") as f:
                f.write(content)

        server_script = os.path.join(ROOT, "mcp_server.py")
        cls.proc = subprocess.Popen(
            [sys.executable, server_script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "MCP_INPUT_DIR": cls.mcp_input, "MCP_LOG_LEVEL": "INFO"},
            cwd=ROOT,
        )
        time.sleep(3)
        assert cls.proc.poll() is None, (
            f"Server exited with code {cls.proc.poll()}: "
            f"{cls.proc.stderr.read(4096).decode('utf-8', errors='replace')}"
        )

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.proc.kill()
        cls.temp_dir.cleanup()

    def _send(self, message: dict) -> dict:
        line = json.dumps(message, ensure_ascii=False) + "\n"
        self.__class__.proc.stdin.write(line.encode("utf-8"))
        self.__class__.proc.stdin.flush()
        for _ in range(60):  # up to 6s timeout
            resp_line = self.__class__.proc.stdout.readline()
            if resp_line:
                return json.loads(resp_line.decode("utf-8"))
            time.sleep(0.1)
        raise TimeoutError("No response from MCP server")

    def test_01_initialize(self):
        resp = self._send({
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
            "id": 1,
        })
        self.assertIn("result", resp)
        self.assertEqual(resp["result"]["serverInfo"]["name"], "patent-agent")
        self.assertIn("tools", resp["result"]["capabilities"])

    def test_02_tools_list(self):
        resp = self._send({
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {},
            "id": 2,
        })
        tools = resp["result"]["tools"]
        self.assertEqual(len(tools), 24)
        for t in tools:
            self.assertIn("name", t)
            self.assertEqual(t["inputSchema"]["type"], "object")
            self.assertIn("算法:", t["description"])
            self.assertIn("禁止结论:", t["description"])
        names = {t["name"] for t in tools}
        for expected in ["get_dataset_summary", "analyze_patent_trend", "analyze_lifecycle"]:
            self.assertIn(expected, names)

    def test_03_call_dataset_summary(self):
        resp = self._send({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "get_dataset_summary", "arguments": {}},
            "id": 3,
        })
        self.assertIn("content", resp["result"])
        text = resp["result"]["content"][0]["text"]
        self.assertIn("total_patents", text)

    def test_04_call_unknown_tool(self):
        resp = self._send({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}},
            "id": 4,
        })
        text = resp["result"]["content"][0]["text"]
        self.assertIn("Unknown tool", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
