#!/usr/bin/env python3
import subprocess
import json
import sys
import uuid

class GrafanaMcpClient:
    def __init__(self):
        self.proc = subprocess.Popen(
            ["npx", "-y", "@opencode/mcp-client", "grafana-mcp-prd"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        # Consume the "Ready" signal
        self.proc.stdout.readline()

    def send(self, method, params):
        req_id = str(uuid.uuid4())
        req = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        self.proc.stdin.write(json.dumps(req) + "\\n")
        self.proc.stdin.flush()
        return req_id

    def recv(self):
        line = self.proc.stdout.readline()
        if not line:
            return None
        return json.loads(line)

    def query_prometheus(self, datasource_uid, expr, end_time, query_type="instant", start_time=None, step=None):
        params = {
            "datasourceUid": datasource_uid,
            "expr": expr,
            "endTime": end_time,
            "queryType": query_type,
        }
        if query_type == "range":
            params["startTime"] = start_time
            params["stepSeconds"] = step

        req_id = self.send("tools/call", {"name": "query_prometheus", "arguments": params})
        
        while True:
            resp = self.recv()
            if resp and resp.get("id") == req_id:
                if resp.get('error'):
                    raise Exception(f"MCP Error: {resp['error']['message']}")
                return resp['result']

    def close(self):
        self.proc.terminate()

if __name__ == "__main__":
    client = GrafanaMcpClient()
    try:
        result = client.query_prometheus("prometheus", "up{job='prometheus'}", "now")
        print(json.dumps(result, indent=2))
    finally:
        client.close()
