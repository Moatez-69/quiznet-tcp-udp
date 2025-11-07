import streamlit as st
import socket
import threading
import json
import time
from datetime import datetime

# Server code
class TCPServer:
    def __init__(self, host='127.0.0.1', port=8888):
        self.host = host
        self.port = port
        self.socket = None
        self.clients = {}
        self.questions = []
        self.current_question = None
        self.game_active = False
        self.answered = set()
        self.lock = threading.Lock()
        self.running = False
       
    def load_questions(self):
        questions = []
        try:
            with open('questions.txt', 'r') as f:
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
            st.error("questions.txt not found!")
        return questions
   
    def start_server(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(5)
            self.running = True
            self.questions = self.load_questions()
            
            while self.running:
                try:
                    self.socket.settimeout(1.0)
                    client_socket, address = self.socket.accept()
                    threading.Thread(target=self.handle_client, args=(client_socket, address), daemon=True).start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"Error accepting connection: {e}")
                    break
        except OSError as e:
            self.running = False
            raise Exception(f"Failed to start server: {e}")
   
    def handle_client(self, client_socket, address):
        while self.running:
            try:
                data = client_socket.recv(1024).decode('utf-8')
                if not data:
                    break
                   
                messages = data.strip().split('\n')
                for msg in messages:
                    if msg:
                        message = json.loads(msg)
                        self.process_message(message, client_socket, address)
                       
            except (ConnectionResetError, BrokenPipeError):
                break
            except json.JSONDecodeError:
                pass
            except Exception as e:
                break
       
        with self.lock:
            if client_socket in self.clients:
                del self.clients[client_socket]
        client_socket.close()
   
    def process_message(self, message, client_socket, address):
        msg_type = message.get('type')
        if msg_type == 'join':
            self.handle_join(message, client_socket, address)
        elif msg_type == 'answer' and self.game_active:
            self.handle_answer(message, client_socket)
   
    def handle_join(self, message, client_socket, address):
        username = message.get('username')
        with self.lock:
            if username and username not in [client['username'] for client in self.clients.values()]:
                self.clients[client_socket] = {
                    'username': username,
                    'address': address,
                    'score': 0
                }
                self.send_message({'type': 'welcome', 'message': f'Welcome {username}!'}, client_socket)
            else:
                self.send_message({'type': 'error', 'message': 'Username already taken'}, client_socket)
                client_socket.close()
   
    def handle_answer(self, message, client_socket):
        with self.lock:
            if client_socket not in self.clients or client_socket in self.answered:
                return
           
            username = self.clients[client_socket]['username']
            answer = message.get('answer')
            question_id = message.get('question_id')
           
            if (self.current_question and
                question_id == self.current_question['id'] and
                answer == self.current_question['correct']):
               
                self.clients[client_socket]['score'] += 10
                self.answered.add(client_socket)
               
                broadcast_msg = {
                    'type': 'result',
                    'message': f'{username} answered correctly! +10 points',
                    'correct_answer': self.current_question['correct'],
                    'first_correct': username
                }
                self.broadcast(broadcast_msg)
                self.send_leaderboard()
   
    def start_game(self):
        self.game_active = True
        for question in self.questions:
            self.current_question = question
            self.answered.clear()
           
            question_msg = {
                'type': 'question',
                'id': question['id'],
                'text': question['text'],
                'options': question['options'],
                'time_limit': 15
            }
            self.broadcast(question_msg)
            time.sleep(15)
           
            if not self.answered:
                timeout_msg = {
                    'type': 'timeout',
                    'message': 'Time\'s up!',
                    'correct_answer': question['correct']
                }
                self.broadcast(timeout_msg)
            else:
                # Send result to all who didn't answer
                result_msg = {
                    'type': 'question_end',
                    'message': 'Question ended',
                    'correct_answer': question['correct']
                }
                self.broadcast(result_msg)
            
            time.sleep(3)
       
        self.end_game()
   
    def end_game(self):
        self.game_active = False
        final_scores = self.get_leaderboard()
        end_msg = {
            'type': 'game_over',
            'message': 'Quiz completed!',
            'final_scores': final_scores
        }
        self.broadcast(end_msg)
   
    def send_leaderboard(self):
        leaderboard = self.get_leaderboard()
        leaderboard_msg = {'type': 'leaderboard', 'scores': leaderboard}
        self.broadcast(leaderboard_msg)
   
    def get_leaderboard(self):
        with self.lock:
            return {client['username']: client['score'] for client in self.clients.values()}
   
    def broadcast(self, message):
        data = (json.dumps(message) + '\n').encode('utf-8')
        with self.lock:
            disconnected_clients = []
            for client_socket in self.clients.keys():
                try:
                    client_socket.send(data)
                except (BrokenPipeError, ConnectionResetError):
                    disconnected_clients.append(client_socket)
            for client in disconnected_clients:
                if client in self.clients:
                    del self.clients[client]
   
    def send_message(self, message, client_socket):
        try:
            data = (json.dumps(message) + '\n').encode('utf-8')
            client_socket.send(data)
        except (BrokenPipeError, ConnectionResetError):
            pass
    
    def stop_server(self):
        self.running = False
        if self.socket:
            self.socket.close()

# Client code
class TCPClient:
    def __init__(self, server_host='localhost', server_port=8888):
        self.server_host = server_host
        self.server_port = server_port
        self.socket = None
        self.username = None
        self.running = False
        self.messages = []
        self.current_question = None
        self.question_end_time = None
        self.lock = threading.Lock()
       
    def connect(self, username):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.server_host, self.server_port))
            self.username = username
            self.running = True
           
            join_msg = {'type': 'join', 'username': username}
            self.send_message(join_msg)
           
            threading.Thread(target=self.listen_for_messages, daemon=True).start()
            return True
           
        except Exception as e:
            self.messages.append(f"Failed to connect: {e}")
            return False
   
    def send_message(self, message):
        try:
            data = (json.dumps(message) + '\n').encode('utf-8')
            self.socket.send(data)
        except Exception as e:
            self.messages.append(f"Error sending message: {e}")
   
    def listen_for_messages(self):
        buffer = ""
        while self.running:
            try:
                data = self.socket.recv(1024).decode('utf-8')
                if not data:
                    break
                   
                buffer += data
                messages = buffer.split('\n')
                buffer = messages.pop()
               
                for msg in messages:
                    if msg:
                        message = json.loads(msg)
                        self.handle_message(message)
                       
            except ConnectionResetError:
                self.messages.append("Connection lost with server")
                break
            except json.JSONDecodeError:
                pass
            except Exception as e:
                break
   
    def handle_message(self, message):
        msg_type = message.get('type')
        with self.lock:
            if msg_type == 'welcome':
                self.messages.append(f"✅ {message['message']}")
            elif msg_type == 'question':
                self.current_question = message
                self.question_end_time = time.time() + message.get('time_limit', 15)
                self.messages.append(f"\n📝 Question {message['id']}: {message['text']}")
            elif msg_type == 'result':
                self.messages.append(f"✅ {message['message']}")
                self.current_question = None
                self.question_end_time = None
            elif msg_type == 'timeout':
                self.messages.append(f"⏰ {message['message']} - Correct: {message['correct_answer']}")
                self.current_question = None
                self.question_end_time = None
            elif msg_type == 'question_end':
                if self.current_question:
                    self.messages.append(f"⏱️ Question ended - Correct answer: {message['correct_answer']}")
                self.current_question = None
                self.question_end_time = None
            elif msg_type == 'leaderboard':
                scores = message['scores']
                leaderboard = "\n📊 Leaderboard:\n" + "\n".join(
                    [f"  {u}: {s} pts" for u, s in sorted(scores.items(), key=lambda x: x[1], reverse=True)]
                )
                self.messages.append(leaderboard)
            elif msg_type == 'game_over':
                self.messages.append(f"\n🏁 {message['message']}")
                self.running = False
            elif msg_type == 'error':
                self.messages.append(f"❌ Error: {message['message']}")
    
    def send_answer(self, answer_letter):
        if self.current_question:
            answer_msg = {
                'type': 'answer',
                'question_id': self.current_question['id'],
                'answer': ord(answer_letter) - 96,
                'username': self.username
            }
            self.send_message(answer_msg)
    
    def disconnect(self):
        self.running = False
        if self.socket:
            self.socket.close()

# Streamlit UI
st.set_page_config(page_title="TCP Quiz Game", page_icon="🎯", layout="wide")

st.title("🎯 TCP Quiz Game")

# Initialize session state
if 'server' not in st.session_state:
    st.session_state.server = None
if 'client' not in st.session_state:
    st.session_state.client = None
if 'server_running' not in st.session_state:
    st.session_state.server_running = False
if 'client_connected' not in st.session_state:
    st.session_state.client_connected = False

# Create tabs
tab1, tab2 = st.tabs(["🖥️ Server", "👤 Client"])

# Server Tab
with tab1:
    st.header("Quiz Server Control")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        server_host = st.text_input("Server Host", value="127.0.0.1", key="srv_host")
        server_port = st.number_input("Server Port", value=8888, min_value=1024, max_value=65535, key="srv_port")
    
    with col2:
        st.write("")
        st.write("")
        if not st.session_state.server_running:
            if st.button("🚀 Start Server", type="primary", use_container_width=True):
                try:
                    st.session_state.server = TCPServer(server_host, server_port)
                    threading.Thread(target=st.session_state.server.start_server, daemon=True).start()
                    time.sleep(0.5)  # Give server time to start
                    if st.session_state.server.running:
                        st.session_state.server_running = True
                        st.success(f"Server started on {server_host}:{server_port}")
                        st.rerun()
                    else:
                        st.error("Failed to start server")
                except Exception as e:
                    st.error(f"Error starting server: {e}")
                    st.info("💡 Tip: Port might be in use. Try a different port or run: `sudo lsof -ti:8888 | xargs kill -9`")
        else:
            if st.button("⏹️ Stop Server", type="secondary", use_container_width=True):
                if st.session_state.server:
                    st.session_state.server.stop_server()
                st.session_state.server_running = False
                st.session_state.server = None
                st.info("Server stopped")
                st.rerun()
    
    if st.session_state.server_running and st.session_state.server:
        st.divider()
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🎮 Start Game", disabled=st.session_state.server.game_active, use_container_width=True):
                threading.Thread(target=st.session_state.server.start_game, daemon=True).start()
                st.success("Game started!")
        
        with col2:
            st.metric("Connected Players", len(st.session_state.server.clients))
        
        # Display connected players
        if st.session_state.server.clients:
            st.subheader("Connected Players")
            leaderboard = st.session_state.server.get_leaderboard()
            for username, score in sorted(leaderboard.items(), key=lambda x: x[1], reverse=True):
                st.write(f"👤 **{username}**: {score} points")
        
        # Display game status
        if st.session_state.server.game_active:
            st.success("🎮 Game is active!")
            if st.session_state.server.current_question:
                st.info(f"Current Question: {st.session_state.server.current_question['text']}")

# Client Tab
with tab2:
    st.header("Quiz Client")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        client_host = st.text_input("Server Host", value="localhost", key="cli_host")
        client_port = st.number_input("Server Port", value=8888, min_value=1024, max_value=65535, key="cli_port")
        username = st.text_input("Username", key="username")
    
    with col2:
        st.write("")
        st.write("")
        st.write("")
        if not st.session_state.client_connected:
            if st.button("🔗 Connect", type="primary", disabled=not username, use_container_width=True):
                client = TCPClient(client_host, client_port)
                if client.connect(username):
                    st.session_state.client = client
                    st.session_state.client_connected = True
                    st.success(f"Connected as {username}")
                    st.rerun()
                else:
                    st.error("Failed to connect")
        else:
            if st.button("🔌 Disconnect", type="secondary", use_container_width=True):
                if st.session_state.client:
                    st.session_state.client.disconnect()
                st.session_state.client_connected = False
                st.session_state.client = None
                st.info("Disconnected")
                st.rerun()
    
    if st.session_state.client_connected and st.session_state.client:
        st.divider()
        
        # Display current question
        if st.session_state.client.current_question:
            question = st.session_state.client.current_question
            
            # Calculate remaining time
            remaining_time = 0
            if st.session_state.client.question_end_time:
                remaining_time = max(0, int(st.session_state.client.question_end_time - time.time()))
            
            # Display timer
            col1, col2 = st.columns([3, 1])
            with col1:
                st.subheader(f"❓ Question {question['id']}")
            with col2:
                if remaining_time > 0:
                    st.metric("⏱️ Time Left", f"{remaining_time}s")
                else:
                    st.metric("⏱️ Time Left", "0s")
            
            st.write(f"**{question['text']}**")
            
            options = ['a', 'b', 'c', 'd']
            col1, col2 = st.columns(2)
            
            for i, option in enumerate(question['options']):
                target_col = col1 if i < 2 else col2
                with target_col:
                    if st.button(f"{options[i].upper()}) {option}", key=f"opt_{i}", use_container_width=True, disabled=remaining_time == 0):
                        st.session_state.client.send_answer(options[i])
                        with st.session_state.client.lock:
                            st.session_state.client.messages.append(f"📤 Submitted answer: {options[i].upper()}")
        else:
            st.info("⏳ Waiting for next question...")
        
        # Display messages
        st.divider()
        st.subheader("📬 Messages")
        message_container = st.container(height=300)
        with message_container:
            if st.session_state.client.messages:
                for msg in st.session_state.client.messages[-10:]:
                    st.text(msg)
            else:
                st.info("Waiting for messages...")
        
        # Auto-refresh
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()

# Footer
st.divider()
st.caption("TCP Quiz Game - Streamlit UI | Made with ❤️")

# Auto-refresh every 1 second when connected for smooth timer
if st.session_state.client_connected or st.session_state.server_running:
    time.sleep(1)
    st.rerun()