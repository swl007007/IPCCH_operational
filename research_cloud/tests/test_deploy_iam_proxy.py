"""iam_proxy against a local upstream: the identity header is added and the client's own copy dropped, Basic
credentials pass through, Content-Length and chunked request bodies arrive whole, responses stream, HEAD/204 carry no
body."""
import http.client
import http.server
import json
import threading
import unittest

import requests

from research_cloud.deploy import iam_proxy


class Upstream(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def reply(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        if self.path == "/empty":
            self.send_response(204)
            self.end_headers()
            return
        payload = json.dumps({"method": self.command, "body": body.decode(), "iam": self.headers.get("X-Serverless-Authorization"),
                              "auth": self.headers.get("Authorization"), "chunked": self.headers.get("Transfer-Encoding")}).encode()
        payload += b"x" * (200_000 if self.path == "/big" else 0)
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    do_GET = do_POST = do_PUT = do_HEAD = reply


class FixedToken:
    def get(self):
        return "TOKEN"


class Proxy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.up = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        threading.Thread(target=cls.up.serve_forever, daemon=True).start()
        target = f"http://127.0.0.1:{cls.up.server_address[1]}"
        cls.px = iam_proxy.Server(("127.0.0.1", 0), iam_proxy.handler(target, FixedToken(), requests.Session()))
        threading.Thread(target=cls.px.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.px.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.px.shutdown()
        cls.up.shutdown()

    def test_paths(self):
        r = requests.post(self.url + "/a", data=b"hello", auth=("u", "p"),
                          headers={"X-Serverless-Authorization": "Bearer client"})
        got = json.loads(r.content)
        self.assertEqual((got["method"], got["body"], got["iam"]), ("POST", "hello", "Bearer TOKEN"))
        self.assertTrue(got["auth"].startswith("Basic "))
        r = requests.put(self.url + "/a", data=iter([b"ab", b"cd", b"ef"]))          # chunked upload
        got = json.loads(r.content)
        self.assertEqual((got["method"], got["body"], got["chunked"]), ("PUT", "abcdef", None))
        r = requests.get(self.url + "/big")
        self.assertEqual(len(r.content) - len(r.content.rstrip(b"x")), 200_000)
        conn = http.client.HTTPConnection("127.0.0.1", self.px.server_address[1])
        conn.request("HEAD", "/a")
        resp = conn.getresponse()
        self.assertEqual((resp.status, resp.read()), (200, b""))
        conn.request("GET", "/empty")                                                  # same connection still usable
        resp = conn.getresponse()
        self.assertEqual((resp.status, resp.read()), (204, b""))
        conn.close()


if __name__ == "__main__":
    unittest.main()
