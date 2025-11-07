import socket
import threading
import json
import time

class TCPServer:
    def __init__(self, host='127.0.0.1', port=8888):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.clients = {}  # {client_socket: {'username': str, 'address': tuple, 'score': int}}
        self.questions = self.load_questions()
        self.current_question = None
        self.game_active = False
        self.answered = set()
        self.lock = threading.Lock()
        self.running = True
       
    def load_questions(self):
        questions = []
        try:
            with open('questions.txt', 'r', encoding='utf-8') as f:
                for line in f:
                    parts = line.strip().split(':')
                    if len(parts) >= 7:
                        questions.append({
                            'id': int(parts[0]),
                            'text': parts[1],
                            'options': parts[2:6],
                            'correct': int(parts[6])
                        })
        except FileNotFoundError:
            print("Error: questions.txt not found!")
            # Create sample questions
            questions = [
                {
                    'id': 1,
                    'text': 'What is 2+2?',
                    'options': ['3', '4', '5', '6'],
                    'correct': 2
                },
                {
                    'id': 2,
                    'text': 'What is the capital of France?',
                    'options': ['London', 'Berlin', 'Paris', 'Madrid'],
                    'correct': 3
                }
            ]
        return questions
   
    def start_server(self):
        try:
            self.socket.bind((self.host, self.port))
            self.socket.listen(5)
            print(f"✅ TCP Quiz Server started on {self.host}:{self.port}")
            print(f"📝 Loaded {len(self.questions)} questions")
            print("⏳ Waiting for players to join...")
           
            # Accept connections
            while self.running:
                try:
                    self.socket.settimeout(1.0)
                    client_socket, address = self.socket.accept()
                    threading.Thread(target=self.handle_client, args=(client_socket, address), daemon=True).start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"❌ Error accepting connection: {e}")
        except OSError as e:
            print(f"❌ Failed to start server: {e}")
            print("💡 Tip: Port might be in use. Try: sudo lsof -ti:8888 | xargs kill -9")
   
    def handle_client(self, client_socket, address):
        print(f"🔗 New connection from {address}")
        buffer = ""
       
        while self.running:
            try:
                data = client_socket.recv(1024).decode('utf-8')
                if not data:
                    break
                
                buffer += data
                messages = buffer.split('\n')
                buffer = messages.pop()  # Keep incomplete message
                   
                for msg in messages:
                    if msg.strip():
                        try:
                            message = json.loads(msg)
                            self.process_message(message, client_socket, address)
                        except json.JSONDecodeError:
                            print(f"⚠️ Invalid JSON from {address}")
                       
            except (ConnectionResetError, BrokenPipeError):
                break
            except Exception as e:
                print(f"❌ Error handling client {address}: {e}")
                break
       
        # Client disconnected
        with self.lock:
            if client_socket in self.clients:
                username = self.clients[client_socket]['username']
                print(f"👋 Player {username} disconnected")
                del self.clients[client_socket]
       
        try:
            client_socket.close()
        except:
            pass
   
    def process_message(self, message, client_socket, address):
        msg_type = message.get('type')
       
        if msg_type == 'join':
            self.handle_join(message, client_socket, address)
        elif msg_type == 'answer' and self.game_active:
            self.handle_answer(message, client_socket)
   
    def handle_join(self, message, client_socket, address):
        username = message.get('username', '').strip()
       
        with self.lock:
            # Check if username is valid and not taken
            existing_usernames = [client['username'] for client in self.clients.values()]
            
            if not username:
                self.send_message({'type': 'error', 'message': 'Username cannot be empty'}, client_socket)
                client_socket.close()
            elif username in existing_usernames:
                self.send_message({'type': 'error', 'message': 'Username already taken'}, client_socket)
                client_socket.close()
            else:
                self.clients[client_socket] = {
                    'username': username,
                    'address': address,
                    'score': 0
                }
                print(f"✅ Player '{username}' joined from {address} (Total: {len(self.clients)})")
                self.send_message({'type': 'welcome', 'message': f'Welcome {username}! Waiting for game to start...'}, client_socket)
                
                # Notify all clients of new player
                self.send_leaderboard()
   
    def handle_answer(self, message, client_socket):
        with self.lock:
            if client_socket not in self.clients or client_socket in self.answered:
                return
           
            username = self.clients[client_socket]['username']
            answer = message.get('answer')
            question_id = message.get('question_id')
           
            # Validate answer
            if not isinstance(answer, int) or answer < 1 or answer > 4:
                return
            
            if not self.current_question or question_id != self.current_question['id']:
                return
            
            # Mark as answered (even if wrong)
            self.answered.add(client_socket)
            
            if answer == self.current_question['correct']:
                # Correct answer
                self.clients[client_socket]['score'] += 10
               
                # Broadcast correct answer
                broadcast_msg = {
                    'type': 'result',
                    'message': f'🎉 {username} answered correctly! +10 points',
                    'correct_answer': self.current_question['correct'],
                    'first_correct': username
                }
                self.broadcast(broadcast_msg)
               
                # Update leaderboard
                self.send_leaderboard()
            else:
                # Wrong answer - notify only the client
                self.send_message({
                    'type': 'wrong_answer',
                    'message': '❌ Wrong answer! Keep trying in the next question.'
                }, client_socket)
   
    def start_game(self):
        if not self.questions:
            print("❌ No questions available!")
            return
        
        if not self.clients:
            print("⚠️ No players connected. Waiting...")
            return
            
        self.game_active = True
        print(f"\n🎮 Starting TCP quiz game with {len(self.clients)} players...")
        print(f"📝 Total questions: {len(self.questions)}\n")
       
        for idx, question in enumerate(self.questions, 1):
            self.current_question = question
            self.answered.clear()
            
            print(f"📤 Sending question {idx}/{len(self.questions)}: {question['text']}")
           
            # Send question to all clients
            question_msg = {
                'type': 'question',
                'id': question['id'],
                'text': question['text'],
                'options': question['options'],
                'time_limit': 15,
                'question_number': idx,
                'total_questions': len(self.questions)
            }
            self.broadcast(question_msg)
           
            # Wait for answers (15 seconds)
            time.sleep(15)
           
            # Send timeout message if no one answered
            if not self.answered:
                timeout_msg = {
                    'type': 'timeout',
                    'message': '⏰ Time\'s up! No correct answers.',
                    'correct_answer': question['correct']
                }
                self.broadcast(timeout_msg)
                print(f"⏰ Question {idx} timeout - no correct answers")
            else:
                # Send question end to all clients
                end_msg = {
                    'type': 'question_end',
                    'message': f'Question {idx} completed!',
                    'correct_answer': question['correct']
                }
                self.broadcast(end_msg)
                print(f"✅ Question {idx} completed - {len(self.answered)} correct answers")
           
            time.sleep(3)  # Pause between questions
       
        # Game over
        self.end_game()
   
    def end_game(self):
        self.game_active = False
        self.current_question = None
        final_scores = self.get_leaderboard()
       
        end_msg = {
            'type': 'game_over',
            'message': '🏁 Quiz completed!',
            'final_scores': final_scores
        }
        self.broadcast(end_msg)
        
        print("\n" + "="*50)
        print("🏁 QUIZ COMPLETED - FINAL SCORES:")
        print("="*50)
        for username, score in sorted(final_scores.items(), key=lambda x: x[1], reverse=True):
            print(f"  {username}: {score} points")
        print("="*50 + "\n")
   
    def send_leaderboard(self):
        leaderboard = self.get_leaderboard()
        leaderboard_msg = {
            'type': 'leaderboard',
            'scores': leaderboard
        }
        self.broadcast(leaderboard_msg)
   
    def get_leaderboard(self):
        with self.lock:
            return {client['username']: client['score'] for client in self.clients.values()}
   
    def broadcast(self, message):
        data = (json.dumps(message) + '\n').encode('utf-8')
        with self.lock:
            disconnected_clients = []
            for client_socket in list(self.clients.keys()):
                try:
                    client_socket.send(data)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    disconnected_clients.append(client_socket)
           
            # Remove disconnected clients
            for client in disconnected_clients:
                if client in self.clients:
                    username = self.clients[client]['username']
                    print(f"⚠️ Removed disconnected client: {username}")
                    del self.clients[client]
   
    def send_message(self, message, client_socket):
        try:
            data = (json.dumps(message) + '\n').encode('utf-8')
            client_socket.send(data)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
    
    def stop_server(self):
        print("\n🛑 Stopping server...")
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        print("✅ Server stopped")

def main():
    print("="*50)
    print("🎯 TCP QUIZ SERVER")
    print("="*50)
    
    host = input("Enter host IP (default 127.0.0.1): ").strip() or "127.0.0.1"
    port_input = input("Enter port (default 8888): ").strip()
    port = int(port_input) if port_input else 8888
    
    server = TCPServer(host, port)
    
    # Start server in a thread
    server_thread = threading.Thread(target=server.start_server, daemon=True)
    server_thread.start()
    
    # Wait for server to start
    time.sleep(1)
    
    print("\n💡 Commands:")
    print("  - Type 'start' to start the game")
    print("  - Type 'players' to see connected players")
    print("  - Type 'quit' or press Ctrl+C to stop the server\n")
    
    try:
        while server.running:
            try:
                cmd = input("Enter command: ").strip().lower()
                
                if cmd == 'start':
                    if server.game_active:
                        print("⚠️ Game is already running!")
                    elif not server.clients:
                        print("⚠️ No players connected! Waiting for players...")
                    else:
                        print(f"🎮 Starting game with {len(server.clients)} players...")
                        game_thread = threading.Thread(target=server.start_game, daemon=True)
                        game_thread.start()
                        
                elif cmd == 'players':
                    if server.clients:
                        print(f"\n👥 Connected Players ({len(server.clients)}):")
                        for client_info in server.clients.values():
                            print(f"  - {client_info['username']} (Score: {client_info['score']})")
                        print()
                    else:
                        print("⚠️ No players connected\n")
                        
                elif cmd == 'quit':
                    break
                    
            except EOFError:
                time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\n\n⚠️ Received interrupt signal...")
    
    server.stop_server()

if __name__ == "__main__":
    main()