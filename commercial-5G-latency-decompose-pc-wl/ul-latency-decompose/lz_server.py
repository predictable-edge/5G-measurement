#!/usr/bin/env python3
import socket
import time
import struct
import threading

# Configuration
SERVER_IP = '0.0.0.0'           # Listen on all interfaces
TIME_SYNC_PORT = 5000           # Port for timestamp service (TCP)
TIME_SYNC_INTERVAL = 1          # Send sync packets every 1 second

# Global variables
client_socket = None            # Socket for connected client
running = True                  # Flag to control thread execution
time_offset = 0.0               # Global time offset between server and client
last_sync_time = 0              # Last time we synced
client_rtt = 0.0                # Round trip time with client

def handle_client(client_sock, client_address):
    """Handle communication with a connected client using TCP for time synchronization"""
    global client_socket, time_offset, last_sync_time, client_rtt
    
    # Store the client socket globally
    client_socket = client_sock
    
    try:
        print(f"New client connection from {client_address}")
        
        # Start time sync with client
        sync_thread = threading.Thread(target=sync_time_with_client, args=(client_sock, client_address))
        sync_thread.daemon = True
        sync_thread.start()
        
        # Keep connection alive
        while running:
            # Check if the socket is still connected
            try:
                # Try to send a small packet (0 bytes) with MSG_PEEK to check connection
                client_sock.recv(1, socket.MSG_PEEK)
            except ConnectionError:
                print(f"Connection lost with {client_address}")
                break
            
            # Sleep to avoid busy waiting
            time.sleep(0.1)
    
    except ConnectionResetError:
        print(f"Connection reset by {client_address}")
    except Exception as e:
        print(f"Error handling client {client_address}: {e}")
    finally:
        # Reset globals when client disconnects
        if client_socket == client_sock:
            client_socket = None
        
        # Close the connection
        client_sock.close()
        print(f"Connection closed with client {client_address}")

def sync_time_with_client(client_sock, client_address):
    """Send time sync packets to client and calculate offset"""
    global time_offset, last_sync_time, client_rtt
    
    while running and client_sock == client_socket:
        try:
            # Get current time
            send_time = time.time()
            
            # Pack timestamp into bytes
            timestamp_bytes = struct.pack('!d', send_time)
            
            # Send timestamp to client
            client_sock.sendall(timestamp_bytes)
            
            # Wait for response
            response = client_sock.recv(8)  # Expecting an 8-byte double
            
            # Record receive time
            receive_time = time.time()
            
            if len(response) == 8:
                # Unpack client's timestamp
                client_timestamp = struct.unpack('!d', response)[0]
                
                # Calculate RTT
                rtt = receive_time - send_time
                
                # Calculate one-way delay (assuming symmetric network)
                one_way_delay = rtt / 2
                
                # Calculate time offset (server time - client time)
                # Adjusted for the one-way delay
                client_time_at_receive = client_timestamp + one_way_delay
                offset = receive_time - client_time_at_receive
                
                # Update global variables
                time_offset = offset
                last_sync_time = receive_time
                client_rtt = rtt
                
                print(f"Time sync with {client_address} - Offset: {offset:.6f}s, RTT: {rtt*1000:.2f}ms")
        
        except ConnectionError:
            # Connection issue, will be cleaned up by the main client handler
            break
        except Exception as e:
            print(f"Error syncing time with {client_address}: {e}")
        
        # Wait for next sync interval
        time.sleep(TIME_SYNC_INTERVAL)

def listen_for_clients():
    """Listen for client connections on TIME_SYNC_PORT using TCP"""
    # Create TCP socket for clients
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Disable Nagle algorithm
    server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    server_socket.bind((SERVER_IP, TIME_SYNC_PORT))
    server_socket.listen(5)  # Allow multiple connections
    
    print(f"Time sync server listening on TCP {SERVER_IP}:{TIME_SYNC_PORT}")
    
    try:
        while running:
            # Accept new connection (old connection will be closed if a new one comes in)
            client_sock, client_address = server_socket.accept()
            # Disable Nagle algorithm for the client socket too
            client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            # Handle this client in a new thread
            client_thread = threading.Thread(
                target=handle_client,
                args=(client_sock, client_address)
            )
            client_thread.daemon = True
            client_thread.start()
    
    except KeyboardInterrupt:
        print("Time sync server shutting down...")
    finally:
        server_socket.close()

def main():
    global running
    
    print("Starting time synchronization server...")
    
    # Start client listener thread (TCP)
    client_thread = threading.Thread(target=listen_for_clients)
    client_thread.daemon = True
    client_thread.start()
    
    print(f"Time sync server running with sync interval {TIME_SYNC_INTERVAL}s")
    print("Press Ctrl+C to exit")
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Time sync server shutting down...")
        running = False

if __name__ == "__main__":
    main()
