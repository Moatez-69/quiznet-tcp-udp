#!/usr/bin/python3 
import socket
import json
import random
import threading
from datetime import datetime

class QuizServer:
    def __init__(self, host='127.0.0.1', port=5555):
        """
        Initialize the TCP Quiz Server
        
        TCP (Transmission Control Protocol) provides:
        - Reliable, ordered delivery of data
        - Connection-oriented communication
        - Error checking and automatic retransmission
        """
        self.host = host
        self.port = port
        
        # SOCKET CREATION: Create a TCP socket
        # AF_INET = IPv4 addressing
        # SOCK_STREAM = TCP protocol (stream of bytes)
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        # Allow socket reuse (helpful during development)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        self.questions = []
        self.clients = {}  # Store connected clients: {address: {'score': 0, 'name': ''}}
        self.load_questions()
        
    def load_questions(self):
        """Load questions from questions.txt file"""
        try:
            with open('../questions.txt', 'r') as f:
                for line in f:
                    parts = line.strip().split('|')
                    if len(parts) == 6:
                        self.questions.append({
                            'question': parts[0],
                            'options': [parts[1], parts[2], parts[3], parts[4]],
                            'correct': int(parts[5])
                        })
            print(f"✅ Loaded {len(self.questions)} questions")
        except FileNotFoundError:
            print("❌ questions.txt not found!")
            
    def start(self):
        """Start the TCP server"""
        try:
            # BIND: Associate socket with address (host, port)
            # This reserves the port for our application
            self.server_socket.bind((self.host, self.port))
            
            # LISTEN: Enable server to accept connections
            # Parameter: max number of queued connections
            self.server_socket.listen(5)
            
            print(f"🚀 TCP Server listening on {self.host}:{self.port}")
            print(f"📊 Quiz ready with {len(self.questions)} questions\n")
            
            while True:
                # ACCEPT: Block until a client connects
                # Returns: (client_socket, client_address)
                # client_socket is a NEW socket for this specific client
                client_socket, client_address = self.server_socket.accept()
                
                print(f"✅ New connection from {client_address}")
                
                # Handle each client in a separate thread
                # This allows multiple clients to connect simultaneously
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, client_address)
                )
                client_thread.daemon = True  # Thread dies when main program exits
                client_thread.start()
                
        except Exception as e:
            print(f"❌ Server error: {e}")
        finally:
            self.server_socket.close()
            
    def handle_client(self, client_socket, client_address):
        """Handle individual client connection"""
        try:
            # RECEIVE player name
            # recv() blocks until data arrives
            # Parameter: buffer size (max bytes to receive at once)
            name_data = client_socket.recv(1024).decode('utf-8')
            player_name = json.loads(name_data)['name']
            
            self.clients[client_address] = {'score': 0, 'name': player_name}
            print(f"👤 Player '{player_name}' joined from {client_address}")
            
            # Send welcome message
            welcome = json.dumps({
                'type': 'welcome',
                'message': f"Welcome {player_name}! Get ready for the quiz!"
            })
            # SEND: Transmit data to client
            # encode() converts string to bytes (sockets work with bytes)
            client_socket.send(welcome.encode('utf-8'))
            
            # Start quiz
            score = 0
            quiz_questions = random.sample(self.questions, min(5, len(self.questions)))
            
            for idx, q in enumerate(quiz_questions, 1):
                # Send question
                question_data = json.dumps({
                    'type': 'question',
                    'number': idx,
                    'total': len(quiz_questions),
                    'question': q['question'],
                    'options': q['options']
                })
                client_socket.send(question_data.encode('utf-8'))
                
                # Receive answer with timeout
                client_socket.settimeout(15.0)  # 15 seconds per question
                try:
                    answer_data = client_socket.recv(1024).decode('utf-8')
                    answer = json.loads(answer_data)['answer']
                    
                    # Check answer
                    is_correct = (answer == q['correct'])
                    if is_correct:
                        score += 1
                        
                    # Send feedback
                    feedback = json.dumps({
                        'type': 'feedback',
                        'correct': is_correct,
                        'correct_answer': q['correct'],
                        'current_score': score
                    })
                    client_socket.send(feedback.encode('utf-8'))
                    
                except socket.timeout:
                    print(f"⏰ {player_name} timed out on question {idx}")
                    timeout_msg = json.dumps({
                        'type': 'feedback',
                        'correct': False,
                        'correct_answer': q['correct'],
                        'current_score': score,
                        'timeout': True
                    })
                    client_socket.send(timeout_msg.encode('utf-8'))
            
            # Send final results
            self.clients[client_address]['score'] = score
            results = json.dumps({
                'type': 'results',
                'score': score,
                'total': len(quiz_questions)
            })
            client_socket.send(results.encode('utf-8'))
            
            print(f"🏁 {player_name} finished with score: {score}/{len(quiz_questions)}")
            
        except Exception as e:
            print(f"❌ Error with client {client_address}: {e}")
        finally:
            # CLOSE: Always close the socket when done
            # This releases the connection and frees resources
            client_socket.close()
            print(f"🔌 Connection closed: {client_address}")

if __name__ == "__main__":
    server = QuizServer()
    server.start()