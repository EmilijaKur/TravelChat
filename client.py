import socket
from threading import Thread
import sys

class Client:
    def __init__(self, host, port):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) #uses TCP
        self.socket.connect((host, port))
        self.nickname = input("Enter your nickname: ").strip()
        self.socket.send(self.nickname.encode())
        Thread(target=self.receive_messages, daemon=True).start()
        self.send_messages()

    # send messages to server
    def send_messages(self):
        while True:
            try:
                message = input()
                if message == "/quit":
                    self.socket.send("/quit".encode())
                    self.socket.close()
                    sys.exit()
                self.socket.send(message.encode())
            except:
                print("Disconnected from server")
                self.socket.close()
                break

    # receive messages from server
    def receive_messages(self):
        while True:
            try:
                message = self.socket.recv(16384).decode()
                if not message:
                    print("Connection closed by server.")
                    break
                # travel data pushes (from RPC) shown in yellow
                if "🌍" in message or "✈" in message or "🌤" in message:
                    print("\033[93m" + message + "\033[0m")
                else:
                    print("\033[92m" + message + "\033[0m")
            except:
                print("Lost connection to server.")
                break

if __name__ == "__main__":
    HOST = input("Server IP: ").strip() or "127.0.0.1"
    PORT = 5000
    Client(HOST, PORT)