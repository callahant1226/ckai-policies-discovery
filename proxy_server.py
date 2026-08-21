#!/usr/bin/env python3
"""Minimal local CORS proxy for testing the CKAI API from a browser.

The CKAI API doesn't send Access-Control-Allow-Origin headers, so a browser
fetch() from a local static page gets blocked by CORS even though the
request itself reaches CKAI fine. This proxy runs on your machine, makes the
request to CKAI server-to-server (not subject to CORS), and hands the
response back to the page with the CORS headers it needs.

Run:
    python3 proxy_server.py

Then point local_api_test.html at http://localhost:8010/proxy (already done).
Uses only the Python standard library - no dependencies to install.

NOTE ON TLS: this disables certificate verification for outgoing requests to
CKAI. Python's default cert bundle doesn't include whatever root CA your
Elsevier network/VPN puts in front of HTTPS (a real cert or a corporate
TLS-inspecting proxy), even though your browser and curl already trust it via
macOS's system trust store. That's fine for a local throwaway test hitting an
internal endpoint over a trusted network - it is NOT something to carry into
the real backend. The real implementation should trust the system cert store
properly (e.g. the `truststore` package) instead of disabling verification.
"""
import json
import ssl
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 8010

_INSECURE_SSL_CONTEXT = ssl._create_unverified_context()


class ProxyHandler(BaseHTTPRequestHandler):
    def _set_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self._set_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')
            return
        self.send_response(404)
        self._set_cors_headers()
        self.end_headers()

    def do_POST(self):
        if self.path != "/proxy":
            self.send_response(404)
            self._set_cors_headers()
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length)
        try:
            envelope = json.loads(raw_body)
            target_url = envelope["targetUrl"]
            payload = envelope["payload"]
        except (json.JSONDecodeError, KeyError) as exc:
            self._respond_json(400, {"error": f"Bad proxy request: {exc}"})
            return

        req = urllib.request.Request(
            target_url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120, context=_INSECURE_SSL_CONTEXT) as resp:
                status = resp.status
                body = resp.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = exc.read()
        except urllib.error.URLError as exc:
            self._respond_json(502, {
                "error": "Could not reach the CKAI target URL from this machine.",
                "detail": str(exc.reason),
                "targetUrl": target_url,
                "hint": "Confirm you're connected to the Elsevier network/VPN.",
            })
            return

        self.send_response(status)
        self._set_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def _respond_json(self, status, obj):
        self.send_response(status)
        self._set_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode())

    def log_message(self, format, *args):
        print("[proxy]", format % args)


if __name__ == "__main__":
    server = HTTPServer(("localhost", PORT), ProxyHandler)
    print(f"CKAI CORS proxy listening on http://localhost:{PORT}")
    print("POST /proxy with {targetUrl, payload} to forward to CKAI.")
    print("WARNING: TLS certificate verification is disabled for outgoing "
          "requests to CKAI. Local throwaway testing only - see the note "
          "at the top of this file.")
    server.serve_forever()
