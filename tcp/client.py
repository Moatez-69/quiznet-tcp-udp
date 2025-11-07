import socket
import json
import threading
import time
import sys

class TCPClient:
    def __init__(self, server_host='localhost', server_port=8888):
        self.server_host = server_host
        self.server_port = server_port
        self.socket = None
        self.username = None
        self.running = False
        self.current_question = None
        self.waiting_for_answer = False
        self.lock = threading.Lock()
       
    def connect(self, username):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0)
            print(f"🔗 Connecting to {self.server_host}:{self.server_port}...")
            self.socket.connect((self.server_host, self.server_port))
            self.socket.settimeout(None)
            
            self.username = username
            self.running = True
           
            # Send join message
            join_msg = {'type': 'join', 'username': username}
            self.send_message(join_msg)
           
            # Start listening thread
            threading.Thread(target=self.listen_for_messages, daemon=True).start()
            return True
           
        except socket.timeout:
            print(f"❌ Connection timeout. Is the server running?")
            return False
        except ConnectionRefusedError:
            print(f"❌ Connection refused. Server might not be running on {self.server_host}:{self.server_port}")
            return False
        except Exception as e:
            print(f"❌ Failed to connect: {e}")
            return False
   
    def send_message(self, message):
        try:
            data = (json.dumps(message) + '\n').encode('utf-8')
            self.socket.send(data)
        except Exception as e:
            print(f"❌ Error sending message: {e}")
            self.running = False
   
    def listen_for_messages(self):
        buffer = ""
        while self.running:
            try:
                data = self.socket.recv(1024).decode('utf-8')
                if not data:
                    print("\n❌ Connection lost with server")
                    self.running = False
                    break
                
                buffer += data
                messages = buffer.split('\n')
                buffer = messages.pop()  # Keep incomplete message
               
                for msg in messages:
                    if msg.strip():
                        try:
                            message = json.loads(msg)
                            self.handle_message(message)
                        except json.JSONDecodeError:
                            print("⚠️ Received invalid JSON")
                       
            except ConnectionResetError:
                print("\n❌ Connection lost with server")
                self.running = False
                break
            except Exception as e:
                print(f"\n❌ Error receiving message: {e}")
                self.running = False
                break
   
    def handle_message(self, message):
        msg_type = message.get('type')
       
        if msg_type == 'welcome':
            sys.stdout.write(f"\n✅ {message['message']}\n")
            sys.stdout.flush()
            
        elif msg_type == 'question':
            with self.lock:
                self.current_question = message
                self.waiting_for_answer = True
            self.display_question(message)
            
        elif msg_type == 'result':
            sys.stdout.write(f"\n🎉 {message['message']}\n")
            sys.stdout.write(f"✅ Correct answer was: Option {message['correct_answer']}\n")
            sys.stdout.flush()
            with self.lock:
                self.current_question = None
                self.waiting_for_answer = False
            
        elif msg_type == 'wrong_answer':
            sys.stdout.write(f"\n{message['message']}\n")
            sys.stdout.flush()
            with self.lock:
                self.waiting_for_answer = False
                
        elif msg_type == 'timeout':
            sys.stdout.write(f"\n⏰ {message['message']}\n")
            sys.stdout.write(f"✅ Correct answer was: Option {message['correct_answer']}\n")
            sys.stdout.flush()
            with self.lock:
                self.current_question = None
                self.waiting_for_answer = False
                
        elif msg_type == 'question_end':
            sys.stdout.write(f"\n✅ {message['message']}\n")
            sys.stdout.write(f"✅ Correct answer was: Option {message['correct_answer']}\n")
            sys.stdout.flush()
            with self.lock:
                self.current_question = None
                self.waiting_for_answer = False
            
        elif msg_type == 'leaderboard':
            self.display_leaderboard(message['scores'])
            
        elif msg_type == 'game_over':
            sys.stdout.write(f"\n{'='*50}\n")
            sys.stdout.write(f"🏁 {message['message']}\n")
            sys.stdout.write(f"{'='*50}\n")
            sys.stdout.flush()
            self.display_final_scores(message['final_scores'])
            self.running = False
            
        elif msg_type == 'error':
            sys.stdout.write(f"\n❌ Error: {message['message']}\n")
            sys.stdout.flush()
            self.running = False
   
    def display_question(self, question):
        # Force flush to ensure display
        sys.stdout.write(f"\n{'='*50}\n")
        sys.stdout.write(f"❓ Question {question.get('question_number', question['id'])}/{question.get('total_questions', '?')}\n")
        sys.stdout.write(f"{'='*50}\n")
        sys.stdout.write(f"\n{question['text']}\n\n")
        
        options = ['a', 'b', 'c', 'd']
        for i, option in enumerate(question['options']):
            sys.stdout.write(f"  {options[i].upper()}) {option}\n")
        
        sys.stdout.write(f"\n⏱️  Time limit: {question['time_limit']} seconds\n")
        sys.stdout.write("─"*50 + "\n")
        sys.stdout.flush()
       
        # Start answer input thread
        threading.Thread(target=self.get_answer_input, args=(question,), daemon=True).start()
   
    def get_answer_input(self, question):
        """Get answer from user with timeout"""
        try:
            sys.stdout.write("\n👉 Your answer (a/b/c/d): ")
            sys.stdout.flush()
            answer = input().strip().lower()
            
            with self.lock:
                if not self.waiting_for_answer:
                    sys.stdout.write("⚠️ Too late! Question already ended.\n")
                    sys.stdout.flush()
                    return
                
                self.waiting_for_answer = False
            
            if answer in ['a', 'b', 'c', 'd']:
                answer_msg = {
                    'type': 'answer',
                    'question_id': question['id'],
                    'answer': ord(answer) - 96,  # Convert a->1, b->2, etc.
                    'username': self.username
                }
                self.send_message(answer_msg)
                sys.stdout.write(f"✅ Submitted answer: {answer.upper()}\n")
                sys.stdout.flush()
            else:
                sys.stdout.write("⚠️ Invalid answer! Please use a, b, c, or d\n")
                sys.stdout.flush()
                
        except EOFError:
            pass
        except Exception as e:
            sys.stdout.write(f"⚠️ Error getting input: {e}\n")
            sys.stdout.flush()
   
    def display_leaderboard(self, scores):
        print(f"\n{'─'*50}")
        print("📊 LEADERBOARD")
        print(f"{'─'*50}")
        
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        for rank, (username, score) in enumerate(sorted_scores, 1):
            medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else "  "
            marker = "👉" if username == self.username else "  "
            print(f"{marker} {medal} {rank}. {username}: {score} points")
        
        print(f"{'─'*50}")
   
    def display_final_scores(self, scores):
        print("\n🏆 FINAL RESULTS 🏆\n")
        
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        for rank, (username, score) in enumerate(sorted_scores, 1):
            if rank == 1:
                medal = "🥇 WINNER!"
            elif rank == 2:
                medal = "🥈 2nd Place"
            elif rank == 3:
                medal = "🥉 3rd Place"
            else:
                medal = f"#{rank}"
            
            marker = ">>> " if username == self.username else "    "
            print(f"{marker}{medal} {username}: {score} points")
        
        print(f"\n{'='*50}")
        print("Thanks for playing! 🎮")
        print(f"{'='*50}\n")
    
    def disconnect(self):
        print("\n👋 Disconnecting...")
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass

def main():
    print("="*50)
    print("🎯 TCP QUIZ CLIENT")
    print("="*50)
    print()
    
    server_host = input("Enter server IP (default localhost): ").strip() or "localhost"
    
    port_input = input("Enter server port (default 8888): ").strip()
    server_port = int(port_input) if port_input else 8888
    
    username = input("Enter your username: ").strip()
    
    if not username:
        print("❌ Username cannot be empty!")
        return
    
    print()
    client = TCPClient(server_host, server_port)
    
    if client.connect(username):
        print(f"✅ Connected successfully as '{username}'")
        print("⏳ Waiting for game to start...\n")
        print("💡 Press Ctrl+C to disconnect\n")
        
        try:
            while client.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n\n⚠️ Received interrupt signal...")
            client.disconnect()
    else:
        print("\n❌ Failed to connect to server")
        print("💡 Make sure the server is running and the address is correct")

if __name__ == "__main__":
    main()