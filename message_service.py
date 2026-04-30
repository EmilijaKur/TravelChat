import json
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from urllib.parse import parse_qs, urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MESSAGES_FILE = os.path.join(BASE_DIR, "data", "messages.json")
file_lock = Lock()  # prevents two threads writing the file at once

def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _read_messages():
    with file_lock:
        return load_json(MESSAGES_FILE)


def _write_messages(messages):
    with file_lock:
        save_json(MESSAGES_FILE, messages)

def save_message(nickname, channel, text):
    """Append a message to the channel's history in messages.json."""
    with file_lock:
        messages = load_json(MESSAGES_FILE)
        if channel not in messages:
            messages[channel] = []
        messages[channel].append({
            "nickname": nickname,
            "text": text,
            "timestamp": datetime.now().isoformat(),
        })
        # keep only last 200 messages per channel
        messages[channel] = messages[channel][-200:]
        save_json(MESSAGES_FILE, messages)
    return True # XML-RPC methods must always return a value

def get_recent_messages(channel, count=50):
    """Return the last N messages from a channel."""
    messages = _read_messages()
    recent = messages.get(channel, [])[-count:]
    # return as a plain list of dicts with string-only values (XML-RPC safe)
    return [
        {
            "nickname": m["nickname"],
            "text": m["text"],
            "timestamp": m["timestamp"],
        }
        for m in recent
    ]

def get_all_channels():
    """returns a list of all channels that have saved messages."""
    messages = _read_messages()
    return list(messages.keys())


class MessageHistoryHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status_code, message):
        self._send_json(status_code, {"error": message})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/channels":
            self._send_json(200, {"channels": get_all_channels()})
            return

        if path.startswith("/messages/"):
            channel = path.split("/", 2)[2].strip().lower()
            if not channel:
                self._send_error(400, "Channel is required.")
                return

            try:
                count = int(parse_qs(parsed.query).get("count", [50])[0])
            except (TypeError, ValueError):
                self._send_error(400, "count must be an integer.")
                return

            self._send_json(200, {"channel": channel, "messages": get_recent_messages(channel, count)})
            return

        self._send_error(404, "Not found.")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path != "/messages":
            self._send_error(404, "Not found.")
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(raw_body or "{}")
        except (ValueError, json.JSONDecodeError):
            self._send_error(400, "Invalid JSON body.")
            return

        nickname = str(payload.get("nickname", "")).strip()
        channel = str(payload.get("channel", "")).strip().lower()
        text = str(payload.get("text", "")).strip()

        if not nickname or not channel or not text:
            self._send_error(400, "nickname, channel, and text are required.")
            return

        save_message(nickname, channel, text)
        self._send_json(201, {"ok": True})

    def log_message(self, format, *args):
        return

if __name__ == "__main__":
    HOST = "localhost"
    PORT = 5002
    try:
        server = ThreadingHTTPServer((HOST, PORT), MessageHistoryHandler)
        print(f"Message service started, running on {HOST}:{PORT}")
        server.serve_forever()
    except KeyboardInterrupt:
        print("===Message service shutting down===")
    except Exception as e:
        print(f"[ERROR] Service failed: {e}")