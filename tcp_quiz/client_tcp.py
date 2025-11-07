#!/usr/bin/python3 
import socket
import json

class QuizClient:
    def __init__(self, host='127.0.0.1', port=5555):
        """
        Initialize TCP Quiz Client
        
        The client initiates connection to the server
        """
        self.host = host
        self.port = port
        self.client_socket = None
        
    def connect(self):
        """Connect to the quiz server"""
        try:
            # Create TCP socket (same as server)
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
            # CONNECT: Establish connection to server
            # This is the TCP 3-way handshake:
            # 1. Client sends SYN
            # 2. Server responds with SYN-ACK
            # 3. Client sends ACK
            self.client_socket.connect((self.host, self.port))
            
            print(f"✅ Connected to server at {self.host}:{self.port}")
            return True
            
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False
            
    def send_name(self, name):
        """Send player name to server"""
        try:
            name_data = json.dumps({'name': name})
            # Send data as bytes
            self.client_socket.send(name_data.encode('utf-8'))
            
            # Receive welcome message
            response = self.client_socket.recv(1024).decode('utf-8')
            return json.loads(response)
            
        except Exception as e:
            print(f"❌ Error sending name: {e}")
            return None
            
    def receive_question(self):
        """Receive question from server"""
        try:
            # Block until data arrives from server
            data = self.client_socket.recv(4096).decode('utf-8')
            return json.loads(data)
            
        except Exception as e:
            print(f"❌ Error receiving question: {e}")
            return None
            
    def send_answer(self, answer):
        """Send answer to server"""
        try:
            answer_data = json.dumps({'answer': answer})
            self.client_socket.send(answer_data.encode('utf-8'))
            
            # Receive feedback
            feedback = self.client_socket.recv(1024).decode('utf-8')
            return json.loads(feedback)
            
        except Exception as e:
            print(f"❌ Error sending answer: {e}")
            return None
            
    def close(self):
        """Close connection"""
        if self.client_socket:
            self.client_socket.close()
            print("🔌 Connection closed")

if __name__ == "__main__":
    # Simple command-line test
    client = QuizClient()
    
    if client.connect():
        name = input("Enter your name: ")
        welcome = client.send_name(name)
        print("welcome")
        
        while True:
            question_data = client.receive_question()
            
            if question_data['type'] == 'question':
                print(f"\nQuestion {question_data['number']}/{question_data['total']}")
                print(question_data['question'])
                for i, option in enumerate(question_data['options'], 1):
                    print(f"{i}. {option}")
                    
                answer = int(input("Your answer (1-4): "))
                feedback = client.send_answer(answer)
                
                if feedback['correct']:
                    print("✅ Correct!")
                else:
                    print(f"❌ Wrong! Correct answer: {feedback['correct_answer']}")
                print(f"Score: {feedback['current_score']}")
                
            elif question_data['type'] == 'results':
                print(f"\n🏁 Quiz finished!")
                print(f"Final Score: {question_data['score']}/{question_data['total']}")
                break
                
        client.close()