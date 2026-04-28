import json
import os
from xmlrpc.server import SimpleXMLRPCServer
from threading import Lock
from datetime import datetime

MESSAGES_FILE = "data/messages.json"
file_lock = Lock() # prevents two threads writing the file at once

def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def save_message(nickname, channel, text):
    """RPC method: append a message to the channel's history in messages.json."""
    with file_lock:
        messages = load_json(MESSAGES_FILE)
        if channel not in messages:
            messages[channel] = []
        messages[channel].append({
            "nickname":  nickname,
            "text":      text,
            "timestamp": datetime.now().isoformat(),
        })
        # keep only last 200 messages per channel
        messages[channel] = messages[channel][-200:]
        save_json(MESSAGES_FILE, messages)
    return True # XML-RPC methods must always return a value

def get_recent_messages(channel, count=50):
    """RPC method: return the last N messages from a channel."""
    messages = load_json(MESSAGES_FILE)
    recent = messages.get(channel, [])[-count:]
    # return as a plain list of dicts with string-only values (XML-RPC safe)
    return [
        {
            "nickname":  m["nickname"],
            "text":      m["text"],
            "timestamp": m["timestamp"],
        }
        for m in recent
    ]
def get_all_channels():
    """returns a list of all channels that have saved messages."""
    with file_lock:
        messages = load_json(MESSAGES_FILE)
        return list(messages.keys())

if __name__ == "__main__":
    HOST = "localhost"
    PORT = 5002
    try:
        server = SimpleXMLRPCServer((HOST, PORT), allow_none=True, logRequests=False)
        server.register_function(save_message,        "save_message")
        server.register_function(get_recent_messages, "get_recent_messages")
        server.register_function(get_all_channels, "get_all_channels")
        print(f"Message service started, running on {HOST}:{PORT}")
        server.serve_forever()
    except KeyboardInterrupt:
        print("===Message service shutting down===")
    except Exception as e:
        print(f"[ERROR] Service failed: {e}")