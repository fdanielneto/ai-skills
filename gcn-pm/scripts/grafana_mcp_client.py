#!/usr/bin/env python3
"""
MCP client for grafana-mcp-prd, running under Claude Code.

Bridges to the remote SSE MCP server via `npx mcp-remote <url>` over stdio and
speaks newline-delimited JSON-RPC. Performs the MCP handshake (initialize +
notifications/initialized) before any tools/call — mcp-remote is a transparent
proxy and does NOT auto-initialize.
"""
import subprocess
import json
import sys
import uuid
import select
from datetime import datetime, timezone

GRAFANA_MCP_SSE_URL = "https://grafana-mcp.svc.talkdeskapp.com/sse"
PROTOCOL_VERSION = "2024-11-05"


class GrafanaMcpClient:
    def __init__(self, url=GRAFANA_MCP_SSE_URL, timeout=60):
        self.timeout = timeout
        self.proc = subprocess.Popen(
            ["npx", "-y", "mcp-remote", url],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,  # mcp-remote logs to stderr; keep stdout clean
            text=True,
            bufsize=1,
        )
        self._handshake()

    def _send(self, method, params, req_id=None):
        """Write one JSON-RPC message. If req_id is None, send a notification."""
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        if req_id is not None:
            msg["id"] = req_id
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def _read_response(self, req_id):
        """Block until the JSON-RPC response with matching id arrives.

        Skips non-JSON stdout noise. Raises on timeout, EOF, or MCP error.
        """
        while True:
            ready, _, _ = select.select([self.proc.stdout], [], [], self.timeout)
            if not ready:
                raise TimeoutError(
                    f"grafana-mcp: no response for id={req_id} within {self.timeout}s "
                    f"(endpoint unreachable? VPN/network required)"
                )
            line = self.proc.stdout.readline()
            if line == "":
                raise ConnectionError("grafana-mcp: stdio closed before response (mcp-remote exited)")
            line = line.strip()
            if not line:
                continue
            try:
                resp = json.loads(line)
            except json.JSONDecodeError:
                continue  # startup / proxy noise on stdout
            if resp.get("id") != req_id:
                continue  # unrelated message
            if resp.get("error"):
                raise Exception(f"MCP Error: {resp['error'].get('message', resp['error'])}")
            return resp.get("result", {})

    def _handshake(self):
        req_id = str(uuid.uuid4())
        self._send(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "gcn-pm", "version": "1.0"},
            },
            req_id=req_id,
        )
        self._read_response(req_id)
        self._send("notifications/initialized", {})  # notification, no id

    def list_tools(self):
        req_id = str(uuid.uuid4())
        self._send("tools/list", {}, req_id=req_id)
        return self._read_response(req_id)

    def _call_tool(self, name, arguments):
        req_id = str(uuid.uuid4())
        self._send("tools/call", {"name": name, "arguments": arguments}, req_id=req_id)
        return self._read_response(req_id)

    @staticmethod
    def _fmt_time(t):
        """The tool requires time as a string. Epoch seconds -> RFC3339 UTC;
        strings (e.g. 'now', 'now-1h', RFC3339) pass through unchanged."""
        if isinstance(t, (int, float)):
            return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return t

    def query_prometheus(self, datasource_uid, expr, end_time, query_type="instant",
                         start_time=None, step=None):
        """Query Prometheus via the grafana-mcp query_prometheus tool.

        Returns {"data": {"resultType": ..., "result": [...]}} so callers can do
        res["data"]["result"]. Raises on MCP/connection error.
        """
        args = {
            "datasourceUid": datasource_uid,
            "expr": expr,
            "endTime": self._fmt_time(end_time),
            "queryType": query_type,
        }
        if query_type == "range":
            args["startTime"] = self._fmt_time(start_time)
            args["stepSeconds"] = step

        result = self._call_tool("query_prometheus", args)
        if isinstance(result, dict) and result.get("isError"):
            raise Exception(f"grafana-mcp tool error: {self._content_text(result)[:300]}")
        return {"data": self._extract_prom_data(result)}

    @staticmethod
    def _content_text(result):
        """Concatenate text parts of an MCP content envelope."""
        if isinstance(result, dict) and isinstance(result.get("content"), list):
            return "".join(
                item.get("text", "")
                for item in result["content"]
                if isinstance(item, dict) and item.get("type") == "text"
            )
        return ""

    @classmethod
    def _extract_prom_data(cls, result):
        """Normalize an MCP tool result into a Prometheus {resultType, result} dict.

        grafana-mcp returns {"data": [ {metric, value|values} ]} — i.e. `data` is the
        series list directly (no resultType/result envelope). Also tolerates the
        native Prometheus shape {"resultType", "result"} if the server ever returns it.
        """
        payload = result
        text = cls._content_text(result)
        if text:
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = {}

        # Native Prometheus shape.
        if isinstance(payload, dict) and "resultType" in payload and "result" in payload:
            return payload

        # grafana-mcp shape: {"data": <series-list | {resultType,result}>}.
        series = None
        if isinstance(payload, dict):
            d = payload.get("data")
            if isinstance(d, dict) and "result" in d:
                return d
            if isinstance(d, list):
                series = d
        elif isinstance(payload, list):
            series = payload

        if series is None:
            series = []
        # Range series carry "values" (matrix); instant carry "value" (vector).
        result_type = "matrix" if (series and isinstance(series[0], dict) and "values" in series[0]) else "vector"
        return {"resultType": result_type, "result": series}

    def close(self):
        try:
            self.proc.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    client = GrafanaMcpClient()
    try:
        # Smoke test: confirm handshake + a trivial instant query.
        result = client.query_prometheus("prometheus", "up{job='prometheus'}", "now")
        print(json.dumps(result, indent=2))
    finally:
        client.close()
