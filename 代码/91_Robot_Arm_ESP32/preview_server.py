import argparse
import json
import re
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WEB_HEADER = ROOT / "web.h"
LIMITS = {
    "lr": (10, 170),
    "fb": (10, 170),
    "ud": (10, 170),
    "grip": (55, 180),
}
DEFAULT_HOME = {"lr": 90, "fb": 90, "ud": 90, "grip": 180}
state = {
    "current": DEFAULT_HOME.copy(),
    "target": DEFAULT_HOME.copy(),
    "home": DEFAULT_HOME.copy(),
}


def load_html():
    source = WEB_HEADER.read_text(encoding="utf-8")
    match = re.search(r'R"rawliteral\((.*?)\)rawliteral";', source, re.DOTALL)
    if not match:
        raise RuntimeError("Could not extract HTML from web.h")
    return match.group(1).lstrip("\r\n")


def clamp(axis, value):
    low, high = LIMITS[axis]
    return max(low, min(high, int(value)))


def snapshot():
    return {
        "current": state["current"].copy(),
        "target": state["target"].copy(),
        "home": state["home"].copy(),
        "ip": "10.10.10.1",
        "uptime": 0,
    }


def move_to(values):
    for axis in LIMITS:
        if axis in values:
            angle = clamp(axis, values[axis])
            state["target"][axis] = angle
            state["current"][axis] = angle


class PreviewHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def send_json(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/":
            body = load_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/status":
            self.send_json(snapshot())
            return

        if parsed.path == "/servo":
            move_to({key: values[0] for key, values in query.items()})
            self.send_json({"ok": True})
            return

        if parsed.path == "/jog":
            axis = query.get("axis", [""])[0]
            delta = int(query.get("delta", ["0"])[0])
            if axis in LIMITS:
                move_to({axis: state["target"][axis] + delta})
            self.send_json(snapshot())
            return

        if parsed.path == "/home":
            move_to(state["home"])
            self.send_json(snapshot())
            return

        if parsed.path == "/home/save":
            state["home"] = state["target"].copy()
            self.send_json(snapshot())
            return

        if parsed.path == "/home/factory":
            state["home"] = DEFAULT_HOME.copy()
            move_to(state["home"])
            self.send_json(snapshot())
            return

        self.send_error(404)

    def do_POST(self):
        if self.path != "/home/config":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", "0"))
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
        values = {axis: form[axis][0] for axis in LIMITS if axis in form}
        move_to(values)
        if form.get("save", ["0"])[0] == "1":
            state["home"] = state["target"].copy()
        self.send_json(snapshot())


def main():
    parser = argparse.ArgumentParser(description="Preview the ESP32 arm web console locally")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    url = f"http://127.0.0.1:{args.port}"
    server = ThreadingHTTPServer(("127.0.0.1", args.port), PreviewHandler)
    print(f"Mechanical arm UI preview: {url}")
    print("Press Ctrl+C to stop. All servo actions are simulated.")
    if args.open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
