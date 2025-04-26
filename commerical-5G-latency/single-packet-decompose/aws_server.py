#!/usr/bin/env python3
import socket
import time
import struct
import threading

# Configuration
SERVER_IP = '0.0.0.0'  # Listen on all interfaces
SERVER_PORT = 5000     # Port for timestamp service

def handle_client(client_socket, client_address):
    """Handle communication with a connected client"""
    try:
        print(f"New connection from {client_address}")
        
        while True:
            # Receive request
            data = client_socket.recv(2048)
            if not data:
                # Connection closed by client
                break
                
            # Get current timestamp
            current_time = time.time()
            
            # Get size of received data
            data_size = len(data)
            
            # Create response of the same size
            # First 8 bytes contain the timestamp
            timestamp_bytes = struct.pack('d', current_time)
            
            # Fill the rest with padding to match the original data size
            # Always ensure we send at least 8 bytes for the complete timestamp
            if data_size < 8:
                # If received data is smaller than 8 bytes, still send full timestamp
                response = timestamp_bytes
            else:
                # If larger, send timestamp + padding
                padding_size = data_size - 8
                padding = data[8:] if len(data) > 8 else b'\x00' * padding_size
                response = timestamp_bytes + padding
            
            # Send response back to the client
            client_socket.sendall(response)
            
            print(f"Timestamp sent to {client_address}, response size: {len(response)} bytes")
    
    except ConnectionResetError:
        print(f"Connection reset by {client_address}")
    except Exception as e:
        print(f"Error handling client {client_address}: {e}")
    finally:
        # Close the connection
        client_socket.close()
        print(f"Connection closed with {client_address}")

def main():
    # Create TCP socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Disable Nagle algorithm
    server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    server_socket.bind((SERVER_IP, SERVER_PORT))
    server_socket.listen(5)  # Allow up to 5 queued connections
    
    print(f"AWS Server running on {SERVER_IP}:{SERVER_PORT}")
    
    try:
        while True:
            # Accept new connection
            client_socket, client_address = server_socket.accept()
            
            # Start a new thread to handle this client
            client_thread = threading.Thread(
                target=handle_client,
                args=(client_socket, client_address)
            )
            client_thread.daemon = True
            client_thread.start()
    
    except KeyboardInterrupt:
        print("Server shutting down...")
    finally:
        server_socket.close()

if __name__ == "__main__":
    main()
