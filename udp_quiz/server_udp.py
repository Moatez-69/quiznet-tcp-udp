#!/usr/bin/env python3
# server_udp.py

import socket
import threading
import json
import time
import os
from typing import Dict, Tuple, Any

HOST = "192.168.164.131"
PORT = 8888
QUESTION_TIME = 10
MIN_PLAYERS = 1


def send_udp_json(sock: socket.socket, addr, obj: Any):
    """Send a JSON object safely to a UDP client."""
    try:
        message = json.dumps(obj) + "\n"
        sock.sendto(message.encode(), addr)
    except Exception as e:
        print("UDP send error to", addr, e)


class UDPQuizServer:
    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.host, self.port))
        self.clients: Dict[str, Tuple[str, int]] = {}  # name -> (ip, port)
        self.scores: Dict[str, int] = {}
        self.lock = threading.Lock()
        self.questions = self.load_questions()
        self.answers: Dict[int, list] = {}  # qid -> list[(name, answer)]
        self.running = True

    def load_questions(self):
        """Load quiz questions from JSON file."""
        path = os.path.join(os.path.dirname(__file__), "questions.json")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def start(self):
        print(f"UDP Quiz server listening on {self.host}:{self.port}")
        threading.Thread(target=self.listen_loop, daemon=True).start()
        try:
            self.wait_for_players()
            self.game_loop()
        except KeyboardInterrupt:
            print("\nShutting down.")
            self.running = False
            self.sock.close()

    def wait_for_players(self):
        print("Waiting for players... (Press Ctrl+C to stop waiting)")
        try:
            while len(self.clients) < MIN_PLAYERS:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Stopped waiting for players.")

    def listen_loop(self):
        """Receive UDP messages and process register/answer events."""
        while self.running:
            try:
                data, addr = self.sock.recvfrom(8192)
                text = data.decode(errors="ignore").strip()
                if not text:
                    continue

                for line in text.splitlines():
                    try:
                        msg = json.loads(line)
                    except Exception:
                        continue

                    msg_type = msg.get("type")
                    if msg_type == "register":
                        name = msg.get("name")
                        if name:
                            with self.lock:
                                self.clients[name] = addr
                                self.scores.setdefault(name, 0)
                            print(f"[UDP] Registered {name} at {addr}")

                    elif msg_type == "answer":
                        name = msg.get("name")
                        qid = int(msg.get("question_id"))
                        ans = msg.get("answer")

                        # ✅ ICI : convertir réponse client (1-based) → serveur (1-based aussi, on garde pareil)
                        if isinstance(ans, int):
                            with self.lock:
                                self.answers.setdefault(qid, []).append((name, ans))
                            print(f"[UDP] Received answer from {name}: qid={qid}, ans={ans}")

            except Exception as e:
                print("UDP listen error:", e)

    def broadcast(self, obj: Any):
        """Send a message to all connected clients."""
        with self.lock:
            for name, addr in list(self.clients.items()):
                send_udp_json(self.sock, addr, obj)

    def game_loop(self):
        """Main loop: send questions, collect answers, send results."""
        print("\nStarting the quiz...\n")
        for q in self.questions:
            qid = int(q["id"])
            text = q["text"]
            choices = q["choices"]
            correct_index = int(q["answer"])  # ✅ maintenant on considère que c’est déjà 1-based dans JSON

            question_msg = {
                "type": "question",
                "question_id": qid,
                "text": text,
                "choices": choices,
                "time": QUESTION_TIME,
            }

            with self.lock:
                self.answers[qid] = []

            # Send question to all clients
            self.broadcast(question_msg)
            print(f"→ Sent question {qid}: {text}")
            time.sleep(QUESTION_TIME)

            # Evaluate answers
            results = []
            with self.lock:
                answers_copy = list(self.answers.get(qid, []))
                players = list(self.scores.keys())

            for player in players:
                player_answer = None
                for n, a in reversed(answers_copy):
                    if n == player:
                        player_answer = a
                        break

                # ✅ ICI : pas de conversion, on compare directement 1-based
                is_correct = (player_answer == correct_index)

                if is_correct:
                    self.scores[player] += 1

                results.append({
                    "name": player,
                    "answer": player_answer,
                    "correct": is_correct
                })

                print(f"[EVAL] {player} -> ans={player_answer}, correct={correct_index}, result={is_correct}")

            # Send reveal (1-based)
            reveal_msg = {
                "type": "reveal",
                "question_id": qid,
                "correct": correct_index,
                "results": results,
                "scores": self.scores
            }

            self.broadcast(reveal_msg)
            time.sleep(3)

        # Send final results
        final_msg = {"type": "final", "scores": self.scores}
        self.broadcast(final_msg)
        print("\nRound finished. Final scores:", self.scores)


if __name__ == "__main__":
    server = UDPQuizServer()
    server.start()
