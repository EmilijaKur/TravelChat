import socket
import json
import os
import sys
import signal 
import xmlrpc.client
from xmlrpc.server import SimpleXMLRPCServer
from threading import Thread, Lock
from datetime import datetime

USERS_FILE    = "data/users.json"
MESSAGES_FILE = "data/messages.json"
def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

class Server:
    Clients=[]
    file_lock = Lock() # prevents two threads writing a file at once
    def __init__(self, HOST, PORT):        
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) #here TCP is implemented
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((HOST, PORT))
        self.socket.listen(10)
        signal.signal(signal.SIGINT, self.shutdown_handler)
        #Connection status flags
        self.msg_service_online = True
        self.travel_service_online = True
        print("=== TravelChat server started ===")
        print(f"Listening on {HOST}:{PORT}\n")

        # RPC client: connects to message_service.py for save/fetch of messages
        self.msg_rpc = xmlrpc.client.ServerProxy("http://localhost:5002/", allow_none=True)
        # RPC server: launched in a daemon thread on port 5001
        # so travel_data.py can call push_to_channel and list_channels
        self._start_rpc_server()
    def shutdown_handler(self, sig, frame):
        """This function runs when you press Ctrl+C and want to shut down server."""
        print("\n\nShutting down TravelChat server ===")
        for client in self.Clients:
            try:
                client["socket"].close()
            except:
                pass        
        # Close main server socket
        self.socket.close()
        print("Server closed. Goodbye!")
        sys.exit(0) 

    def _start_rpc_server(self):
        rpc = SimpleXMLRPCServer(("localhost", 5001), allow_none=True, logRequests=False)
        rpc.register_function(self.rpc_push_to_channel, "push_to_channel")
        rpc.register_function(self.rpc_list_channels,   "list_channels")
        Thread(target=rpc.serve_forever, daemon=True).start()
        

    def rpc_push_to_channel(self, channel, message):
        # called by travel_data.py to push a weather/flight update into a channel
        self.broadcast_message("__travel__", f"🌤 [{channel}] {message}", channel)
        return True

    def rpc_list_channels(self):
        # called by travel_data.py to know which channels are currently active
        return list(set(c["channel"] for c in Server.Clients if c["channel"] is not None))

    def save_user(self, nickname, channel):
        """Creates or updates entry by nickname."""
        with self.file_lock:
            users = load_json(USERS_FILE)
            users[nickname] = {
                "nickname":   nickname,
                "channel":    channel,
                "last_seen":  datetime.now().isoformat(),
                # Perhaps RPC: in future, user preferences (home city, language)
                
            }
            save_json(USERS_FILE, users)

    def save_message(self, nickname, channel, text):
        """Append a message to the channel's message history."""
        # RPC: forwards to message_service.py (port 5002) instead of writing JSON directly
        # chat continues even if message_service is down — message just won't be saved
        try:
            self.msg_rpc.save_message(nickname, channel, text)
            if not self.msg_service_online:
                print("[INFO] Connection restored to message service.")
                self.msg_service_online = True
        except Exception as e:
            if self.msg_service_online:
                print("[ERROR] Lost connection to message service. History will not be saved.")
                self.msg_service_online = False

    def get_recent_messages(self, channel, count=50):
        """Return last 50 messages from a channel for the join history display."""
        # RPC: fetches from message_service.py (port 5002) running as a separate process
        try:
            messages = self.msg_rpc.get_recent_messages(channel, count)
            if not self.msg_service_online:
                print("[INFO] Connection restored to message service.")
                self.msg_service_online = True
            return messages
        except Exception as e:
            if self.msg_service_online:
                print("[ERROR] Cannot fetch history: message service is offline.")
                self.msg_service_online = False
            return [] # return empty so _send_history degrades gracefully
    
    def broadcast_message(self, sender_name, message, channel=None):
        for client in Server.Clients:
            if client["nickname"] != sender_name:
                if channel is None or client["channel"] == channel:
                    try:
                        client["socket"].send(message.encode())
                    except:
                        pass   
    
    def private_message(self, sender_name, target_name, message):
        for client in Server.Clients:
            if client["nickname"] == target_name:
                try:
                    client["socket"].send(
                        f"[PM from {sender_name}]: {message}".encode()
                    )
                except:
                    pass
                return
        # sender gets notified if target_name not found
        for client in Server.Clients:
            if client["nickname"] == sender_name:
                client["socket"].send(
                    f"User '{target_name}' not found or offline.".encode()
                )
                return
            
    def send_to(self, nickname, message):
        """Send a message to one specific connected user."""
        for client in Server.Clients:
            if client["nickname"] == nickname:
                try:
                    client["socket"].send(message.encode())
                except:
                    pass
                return
            
    def listen(self):
        try:
            while True:
                client_socket, address = self.socket.accept()
                print("Connection from:", address)
                nickname = client_socket.recv(1024).decode()
                client = {
                "nickname": nickname,
                "socket": client_socket,
                "channel": None,
                }
                Server.Clients.append(client)
                self.save_user(nickname, "general")
                client_socket.send(self._welcome(nickname).encode())
                # show recent history for #general
                """self._send_history(nickname, "general")
                self.broadcast_message(
                    nickname,
                    nickname + " has joined the chat!",
                    "general"
                )"""
                Thread(target=self.handle_new_client, args=(client,), daemon=True).start()
        except KeyboardInterrupt:
            print("\nShutting down server...")
            for client in Server.Clients:
                try:
                    client["socket"].send("Server shut down".encode())
                    client["socket"].close()
                except:
                    pass
            self.socket.close()
            print("Server closed.")

    def _welcome(self, nickname):
        return (
            f"\n🌍 Welcome to TravelChat, {nickname}!\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Share tips, ask questions, explore the world.\n\n"
            "Commands:\n"
            "  /join <city>        → join a city/country channel\n"
            "  /channels           → list active channels\n"
            "  /who                → who is in your channel\n"
            "  /history            → show recent messages\n"
            "  /pm <user> <msg>    → private message a traveller\n"
            "  /quit               → disconnect\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Start by joining a channel: /join <city>  e.g. /join helsinki\n"
        )
    
    def _send_history(self, nickname, channel):
        """Send last 50 messages of a channel to the user who just joined."""
        recent = self.get_recent_messages(channel)
        if not recent:
            self.send_to(nickname, f"  (no messages yet in #{channel})\n")
            return
        self.send_to(nickname, f"\n  ── last messages in #{channel} ──")
        for m in recent:
            dt = datetime.fromisoformat(m["timestamp"])
            ts = dt.strftime("%d %b %Y")  # e.g. "18 Apr 2026"
            self.send_to(nickname, f" [{ts}] {m['nickname']}: {m['text']}\n")
        self.send_to(nickname, "  ─────────────────────────────\n")

    def handle_new_client(self, client):
        nickname = client["nickname"]
        sock = client["socket"]
        while True:
            try:
                message =sock.recv(1024).decode().strip()
                if not message:
                    break
                # only /join, /channels, and /quit are allowed before picking a channel
                if client["channel"] is None:
                    if message.startswith("/join "):
                        pass  # handled below in the normal /join block
                    elif message == "/channels":
                        pass  # handled below
                    elif message == "/quit":
                        break
                    else:
                        self.send_to(nickname, "👉 Please join a channel first: /join <city>")
                        continue

                # join channel
                if message.startswith("/join "):
                    new_channel = message.split(" ", 1)[1].lower().strip()
                    old_channel = client["channel"]
                    if new_channel == old_channel:
                        self.send_to(nickname, f"You are already in #{new_channel}.")
                        continue
                    client["channel"] = new_channel
                    self.save_user(nickname, new_channel)
                    if old_channel is not None:
                        self.broadcast_message(nickname, f"{nickname} left #{old_channel}", old_channel)
                    self.broadcast_message(nickname, f"✈  {nickname} joined #{new_channel}", new_channel)
                    self.send_to(nickname, f"\n✈  Joined #{new_channel}!\n")
                    # show history of new channel
                    self._send_history(nickname, new_channel)
                    try:
                        travel_rpc = xmlrpc.client.ServerProxy("http://localhost:5003/", allow_none=True)
                        snapshot = travel_rpc.get_snapshot(new_channel)
                        if not self.travel_service_online:
                            print(f"[INFO] Connection restored to travel data service.")
                            self.travel_service_online= True
                        if snapshot:
                            self.send_to(nickname, snapshot)
                    except Exception:
                         if self.travel_service_online:
                            print(f"[ERROR] Travel Data Service is offline. Weather updates disabled.")
                            self.travel_service_online = False

                #see active channels
                elif message == "/channels":
                    active_now= set(c["channel"] for c in Server.Clients if c["channel"] is not None)
                    try:
                        recorded_channels = set(self.msg_rpc.get_all_channels())
                    except:
                        recorded_channels = set()
                        print("[WARN] Could not fetch channel list from message_service")
                    all_channels = active_now.union(recorded_channels)
                    if all_channels:
                        formatted = []
                        for c in sorted(all_channels):
                            status = "(active)" if c in active_now else ""
                            formatted.append(f"#{c}{status}")            
                        self.send_to(nickname, "Available channels: " + "  ".join(formatted))
                    else:
                        self.send_to(nickname, "No active channels yet — be the first! /join <city>")

                #see who is in current channel
                elif message == "/who":
                    ch = client["channel"]
                    members = [c["nickname"] for c in Server.Clients if c["channel"] == ch]
                    self.send_to(nickname, f"In #{ch}: {', '.join(members)}")

                #show recent messages
                elif message == "/history":
                    self._send_history(nickname, client["channel"])

                # private message
                elif message.startswith("/pm "):
                    parts = message.split(" ", 2)
                    if len(parts) < 3:
                        self.send_to(nickname, "Usage: /pm <user> <message>")
                    else:
                        _, target, pm_text = parts
                        self.private_message(nickname, target, pm_text)

                # quit sending messages
                elif message == "/quit":
                    break

                # normal message
                else:
                    ch= client["channel"]
                    formatted=f"[#{ch}] {nickname}: {message}"
                    self.broadcast_message(nickname, formatted, ch)
                    self.save_message(nickname, ch, message)
            except:
                break
        print(nickname, "disconnected")
        if client in Server.Clients:
            Server.Clients.remove(client)
        self.broadcast_message(nickname, f"👋 {nickname} left the chat.", client["channel"])
        self.save_user(nickname, client["channel"])  # update last_seen
        sock.close()

if __name__ == "__main__":
    HOST = "0.0.0.0"
    PORT = 5000
    server = Server(HOST, PORT)
    server.listen()