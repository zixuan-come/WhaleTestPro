"""Opt-in real Nginx validation using disposable containers with no public ports."""
import json
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(os.environ.get("WHALE_NGINX_DNS_INTEGRATION") != "1",
    reason="Requires opt-in temporary Docker network and containers")

ECHO_SERVER = """
import json, os
from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.reply()
    def do_POST(self):
        self.reply()
    def reply(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        data = json.dumps(dict(backend=os.environ['ECHO_GENERATION'], method=self.command,
                               path=self.path, body=body.decode('utf-8'))).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def log_message(self, *args):
        pass
HTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
"""


def test_backend_ip_replacement_recovers_without_reloading_frontend(tmp_path):
    prefix = "wtp-proxy-fix-" + uuid4().hex[:8]
    network = prefix + "-net"
    old, new, proxy = [prefix + suffix for suffix in ("-old", "-new", "-proxy")]
    created, observations = [], []

    def docker(*args, check=True):
        return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=45, check=check)

    def echo(path, *, post=False, generation=None):
        command = ["exec", proxy, "wget", "-T", "7", "-q", "-O", "-"]
        if post:
            command += ["--post-data", "literal=a%2Bb&payload=two+words"]
        command.append("http://127.0.0.1" + path)
        until, last = time.monotonic() + 25, None
        while time.monotonic() < until:
            result = docker(*command, check=False)
            try:
                value = json.loads(result.stdout)
            except (ValueError, TypeError):
                last = result.stderr
            else:
                if generation is None or value["backend"] == generation:
                    return value
                last = value
            time.sleep(0.25)
        raise AssertionError(f"Proxy did not recover: {last}")

    def check_routes(generation):
        routes = [("/health/ready", False), ("/reports/executions", False), ("/auth/login", True),
                  ("/regression/run", True), ("/interfaces/7/run", True), ("/cases/7/run", True),
                  ("/cases/chain", True), ("/scenarios/7/run", True), ("/scenarios/7/debug", True),
                  ("/suites/7/run", True), ("/traffic/replay/7", True)]
        query = "?q=two%20words&plus=a%2Bb&repeat=one&repeat=two"
        for path, post in routes:
            result = echo("/api" + path + query, post=post, generation=generation)
            assert result["path"] == path + query
            assert result["method"] == ("POST" if post else "GET")
            assert result["body"] == ("literal=a%2Bb&payload=two+words" if post else "")
            observations.append(result)

    try:
        docker("network", "create", "--internal", "--label", "codex.review=isolated-upstream-regression", network)
        for name, generation in ((old, "old"),):
            docker("run", "--rm", "-d", "--name", name, "--network", network, "--network-alias", "app",
                   "-e", f"ECHO_GENERATION={generation}", "python:3.10-slim", "python", "-u", "-c", ECHO_SERVER)
            created.append(name)
        docker("run", "--rm", "-d", "--name", proxy, "--network", network,
               "--mount", f"type=bind,source={ROOT / 'frontend' / 'nginx.conf'},target=/etc/nginx/conf.d/default.conf,readonly",
               "nginx:alpine")
        created.append(proxy)
        docker("exec", proxy, "nginx", "-t")
        nginx_version = docker("exec", proxy, "nginx", "-v").stderr.strip()
        proxy_id = docker("inspect", "--format", "{{.Id}}", proxy).stdout.strip()
        check_routes("old")
        docker("run", "--rm", "-d", "--name", new, "--network", network, "--network-alias", "app",
               "-e", "ECHO_GENERATION=new", "python:3.10-slim", "python", "-u", "-c", ECHO_SERVER)
        created.append(new)
        docker("stop", old)
        check_routes("new")  # No reload, restart or recreation of the proxy.
        assert docker("inspect", "--format", "{{.Id}}", proxy).stdout.strip() == proxy_id
        config = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
        assert config.count("proxy_read_timeout 660s;") == 2
        assert config.count("proxy_pass http://$api_backend;") == 3
        output = {"nginx": nginx_version, "frontend_recreated": False,
                  "routes_verified": len(observations), "observations": observations}
        result_path = Path(os.environ.get("WHALE_NGINX_DNS_RESULT_PATH", tmp_path / "nginx-upstream.json"))
        result_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        for name in reversed(created):
            docker("rm", "-f", name, check=False)
        docker("network", "rm", network, check=False)
