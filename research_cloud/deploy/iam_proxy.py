"""Loopback proxy to the IAM-protected Cloud Run staging service (operator workstation only).

The staging revision runs with ``--no-allow-unauthenticated``. MLflow clients (SDK, ``workspace_roles``,
``feature_list_map``, the access matrix) speak Basic auth and cannot add a Google identity token, so this proxy, bound
to 127.0.0.1 only, forwards each request to the service URL with the operator's identity token in
``X-Serverless-Authorization`` (Cloud Run checks IAM on it and leaves ``Authorization`` - the MLflow Basic
credentials - to the container). The token comes from ``gcloud auth print-identity-token``, is refreshed every 30
minutes and is never logged.

Supported and tested (``tests/test_deploy_iam_proxy.py``): GET/POST/PUT/PATCH/DELETE/HEAD; request bodies with
``Content-Length`` or ``Transfer-Encoding: chunked`` are read whole (buffered in memory) and forwarded with a
``Content-Length``; response bodies stream back chunked; HEAD, 204 and 304 responses carry no body. Limitations: no
WebSocket/upgrade, no ``Expect: 100-continue`` handshake, request bodies are not streamed. Checks made through it are
evidence of MLflow behaviour behind Cloud Run IAM with this proxy as transport, not of direct client-to-Cloud-Run
transport. MLflow authentication is unchanged: every content route still needs Basic credentials. (``gcloud run
services proxy`` would install an SDK component into the shared SDK directory, which is not modified.)

  python -m research_cloud.deploy.iam_proxy --target https://SERVICE.run.app --port 8091
"""
import argparse
import http.server
import socketserver
import subprocess
import sys
import threading
import time

import requests

HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding",
       "upgrade", "host", "content-length", "x-serverless-authorization"}


class Token:
    def __init__(self, ttl=1800):
        self.ttl, self.value, self.at, self.lock = ttl, None, 0.0, threading.Lock()

    def get(self):
        with self.lock:
            if self.value is None or time.time() - self.at > self.ttl:
                self.value = subprocess.run(["gcloud", "auth", "print-identity-token", "--quiet"], capture_output=True,
                                            text=True, check=True).stdout.strip()
                self.at = time.time()
            return self.value


def handler(target, token, session):
    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):       # method, path and status only; never headers
            sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

        def forward(self):
            body = self.read_body()
            headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
            headers["X-Serverless-Authorization"] = f"Bearer {token.get()}"
            r = session.request(self.command, target + self.path, headers=headers, data=body, stream=True,
                                allow_redirects=False, timeout=(30, 3600))
            bodyless = self.command == "HEAD" or r.status_code in (204, 304) or 100 <= r.status_code < 200
            self.send_response(r.status_code)
            for k, v in r.raw.headers.items():
                if k.lower() not in HOP or (bodyless and k.lower() == "content-length"):
                    self.send_header(k, v)
            if bodyless:
                self.end_headers()
                r.close()
                return
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for chunk in r.raw.stream(1 << 16, decode_content=False):
                self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
            self.wfile.write(b"0\r\n\r\n")
            r.close()

        def read_body(self):
            if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
                parts = []
                while True:
                    size = int(self.rfile.readline().split(b";")[0].strip() or b"0", 16)
                    if size == 0:
                        while self.rfile.readline() not in (b"\r\n", b"\n", b""):   # trailers
                            pass
                        return b"".join(parts)
                    parts.append(self.rfile.read(size))
                    self.rfile.readline()
            length = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(length) if length else None

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = forward

    return Handler


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--port", type=int, default=8091)
    args = ap.parse_args(argv)
    token = Token()
    token.get()                                  # fail at start if no identity token
    server = Server(("127.0.0.1", args.port), handler(args.target.rstrip("/"), token, requests.Session()))
    sys.stderr.write(f"listening on 127.0.0.1:{args.port} -> {args.target}\n")
    server.serve_forever()


if __name__ == "__main__":
    sys.exit(main())
