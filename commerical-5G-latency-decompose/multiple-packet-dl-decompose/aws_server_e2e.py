#!/usr/bin/env python3
import socket
import time
import struct
import threading
import os
import random

# Configuration
SERVER_IP = '0.0.0.0'  # Listen on all interfaces
SERVER_SYNC_PORT = 5000     # Port for timestamp service
PHONE_SERVER_PORT = 5002    # Port for phone client connections

def handle_pc_client(client_socket, client_address):
    """Handle communication with a connected PC client"""
    try:
        print(f"New PC connection from {client_address}")
        
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
        print(f"Error handling PC client {client_address}: {e}")
    finally:
        # Close the connection
        client_socket.close()
        print(f"Connection closed with PC client {client_address}")

def handle_phone_client(client_socket, client_address):
    """Handle communication with a connected phone client"""
    try:
        print(f"New phone connection from {client_address}")
        
        # Disable Nagle algorithm for the client socket
        client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        
        # Receive parameters from phone client
        # Parameters are packed as (num_requests, interval, bytes_per_request) in a struct
        # Format: !iii = 4-byte int + 4-byte int + 4-byte int = 12 bytes total
        param_bytes = client_socket.recv(12)  # 4 bytes + 4 bytes + 4 bytes
        if not param_bytes or len(param_bytes) < 12:
            print(f"Failed to receive parameters from {client_address}")
            return
            
        # Parse parameters
        try:
            num_requests, interval_ms, bytes_per_request = struct.unpack('!iii', param_bytes)
            
            print(f"Received parameters from {client_address}:")
            print(f"  - Number of requests: {num_requests}")
            print(f"  - Interval: {interval_ms}ms (not used in trigger mode)")
            print(f"  - Bytes per request: {bytes_per_request}")
            
            # Send acknowledgment
            client_socket.sendall(b'ACK')
            
            # Wait for trigger packets and send data
            send_data_to_phone(client_socket, client_address, num_requests, bytes_per_request)
            
        except struct.error as e:
            print(f"Invalid parameters received from {client_address}: {e}")
            client_socket.sendall(b'ERR')
            
    except ConnectionResetError:
        print(f"Connection reset by phone client {client_address}")
    except Exception as e:
        print(f"Error handling phone client {client_address}: {e}")
    finally:
        # Close the connection
        client_socket.close()
        print(f"Connection closed with phone client {client_address}")

def send_data_to_phone(client_socket, client_address, num_requests, bytes_per_request):
    """Send data packets to the phone client based on trigger packets"""
    try:
        print(f"Ready to send {num_requests} requests to {client_address} when triggered")
        
        requests_sent = 0
        
        while requests_sent < num_requests:
            # Wait for trigger packet from client
            trigger = client_socket.recv(4)
            if not trigger:
                print(f"Connection closed by client during trigger wait")
                break
                
            # Check if it's a valid trigger packet (we'll use 'TRIG' as the trigger)
            if trigger != b'TRIG':
                print(f"Received invalid trigger packet: {trigger}")
                continue
                
            # Get current timestamp
            current_time = time.time()
            
            # Create header with timestamp and packet size
            header = struct.pack('!dI', current_time, bytes_per_request)
            
            # Combine header and data into a single message
            combined_message = header
            
            # Send combined message in a single call
            client_socket.sendall(combined_message)
            
            requests_sent += 1
            print(f"Sent request {requests_sent}/{num_requests} to {client_address}: {bytes_per_request} bytes")
                
        print(f"Completed sending all {requests_sent}/{num_requests} requests to {client_address}")
        
    except ConnectionResetError:
        print(f"Connection reset by phone client {client_address} during data transmission")
    except Exception as e:
        print(f"Error sending data to phone client {client_address}: {e}")

def listen_for_pc_clients():
    """Listen for PC client connections on SERVER_SYNC_PORT"""
    # Create TCP socket for PC clients
    pc_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    pc_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Disable Nagle algorithm
    pc_server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    pc_server_socket.bind((SERVER_IP, SERVER_SYNC_PORT))
    pc_server_socket.listen(5)  # Allow up to 5 queued connections
    
    print(f"AWS Server listening for PC clients on {SERVER_IP}:{SERVER_SYNC_PORT}")
    
    try:
        while True:
            # Accept new connection
            client_socket, client_address = pc_server_socket.accept()
            
            # Start a new thread to handle this client
            client_thread = threading.Thread(
                target=handle_pc_client,
                args=(client_socket, client_address)
            )
            client_thread.daemon = True
            client_thread.start()
    
    except KeyboardInterrupt:
        print("PC server shutting down...")
    finally:
        pc_server_socket.close()

def listen_for_phone_clients():
    """Listen for phone client connections on PHONE_SERVER_PORT"""
    # Create TCP socket for phone clients
    phone_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    phone_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Disable Nagle algorithm
    phone_server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    phone_server_socket.bind((SERVER_IP, PHONE_SERVER_PORT))
    phone_server_socket.listen(5)  # Allow up to 5 queued connections
    
    print(f"AWS Server listening for phone clients on {SERVER_IP}:{PHONE_SERVER_PORT}")
    
    try:
        while True:
            # Accept new connection
            client_socket, client_address = phone_server_socket.accept()
            
            # Start a new thread to handle this client
            client_thread = threading.Thread(
                target=handle_phone_client,
                args=(client_socket, client_address)
            )
            client_thread.daemon = True
            client_thread.start()
    
    except KeyboardInterrupt:
        print("Phone server shutting down...")
    finally:
        phone_server_socket.close()

def main():
    # Start PC client listener thread
    pc_thread = threading.Thread(target=listen_for_pc_clients)
    pc_thread.daemon = True
    pc_thread.start()
    
    # Start phone client listener thread
    phone_thread = threading.Thread(target=listen_for_phone_clients)
    phone_thread.daemon = True
    phone_thread.start()
    
    print(f"AWS Server running with both PC and phone listeners")
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Server shutting down...")

if __name__ == "__main__":
    main()
