import socket
import threading
import json
import time
import sys
 
# === Color helpers for terminal output ===
def color(code): return lambda s: f"\033[{code}m{s}\033[0m"
CYAN = color("96")
GREEN = color("92")
YELLOW = color("93")
RED = color("91")
MAGENTA = color("95")
 
# === UDP Quiz Client ===
class UDPQuizClient:
    def __init__(self):
        print(MAGENTA("=== UDP Quiz Client ==="))
        self.username = input(YELLOW("Enter your username: ")).strip() or "Player"
        self.server_ip = input(YELLOW("Enter server IP (default 127.0.0.1): ")).strip() or "127.0.0.1"
        self.server_port = 8888
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(5)
        self.running = True
 
    # Register with the server
    def register(self):
        reg = {"type": "register", "name": self.username}
        self.sock.sendto((json.dumps(reg) + "\n").encode(), (self.server_ip, self.server_port))
        print(GREEN(f"[+] Joined the quiz as {self.username}"))
        print(GREEN("[+] Waiting for the quiz to start...\n"))
 
    # Listen for server messages
    def listen(self):
        while self.running:
            try:
                data, _ = self.sock.recvfrom(4096)
                msg = data.decode().strip()
                if not msg:
                    continue
                try:
                    m = json.loads(msg)
                except json.JSONDecodeError:
                    print(YELLOW(f"Unrecognized message: {msg}"))
                    continue
                self.handle_message(m)
            except socket.timeout:
                continue
            except Exception as e:
                print(RED(f"Error: {e}"))
                self.running = False
                break
 
    def handle_message(self, msg):
        t = msg.get("type")
        if t == "question":
            self.show_question(msg)
        elif t == "reveal":
            self.show_reveal(msg)
        elif t == "final":
            self.show_final(msg)
        elif t == "info":
            print(CYAN(f"\n[INFO] {msg.get('message', '')}"))
        else:
            print(YELLOW(f"Unknown message type: {t}"))
 
    def show_question(self, msg):
        print(CYAN("\nNEW QUESTION"))
        print(CYAN(f"{msg['text']}"))
        for i, opt in enumerate(msg["choices"], 1):
            print(f"   {i}. {opt}")
 
        while True:
            answer = input(YELLOW("Your answer (1-4): ")).strip()
            if answer.isdigit() and 1 <= int(answer) <= 4:
                break
            print(RED("Invalid choice. Enter a number between 1 and 4."))
 
        ans = {
            "type": "answer",
            "name": self.username,
            "question_id": msg["question_id"],
            "answer": int(answer) - 1  # server expects 0-indexed answer
        }
        self.sock.sendto((json.dumps(ans) + "\n").encode(), (self.server_ip, self.server_port))
 
    def show_reveal(self, msg):
        print(GREEN("\nResults for this question:"))
        correct = msg["correct"]
        for res in msg["results"]:
            mark = "Correct" if res["correct"] else "Wrong"
            print(f"{res['name']}: {mark} (answered {res['answer']})")
        print(GREEN(f"\nCorrect answer: {correct}"))
        print(MAGENTA("Current scores:"))
        for n, s in msg["scores"].items():
            print(f"  {n}: {s}")
 
    def show_final(self, msg):
        print(MAGENTA("\nFINAL SCORES"))
        for name, score in msg["scores"].items():
            print(f"{name}: {score}")
        print(GREEN("\nThanks for playing!"))
        self.running = False
        time.sleep(2)
        sys.exit(0)
 
    def start(self):
        self.register()
        listen_thread = threading.Thread(target=self.listen, daemon=True)
        listen_thread.start()
        try:
            while self.running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            print(RED("\nExiting the quiz."))
            self.running = False
 
# === Run Client ===
if __name__ == "__main__":
    client = UDPQuizClient()
    client.start()