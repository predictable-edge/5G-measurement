#!/usr/bin/env python3
import socket
import time
import struct
import threading
import os
import random

# Configuration
SERVER_IP = '0.0.0.0'  # Listen on all interfaces
SERVER_SYNC_PORT = 5000     # Port for timestamp service (TCP)
PHONE_SERVER_PORT = 5002    # Port for phone client connections (UDP)
MAX_UDP_SEGMENT = 4096      # Maximum UDP segment size
UDP_BUFFER_SIZE = 4194304   # Buffer size for UDP socket (4MB)

def handle_pc_client(client_socket, client_address):
    """Handle communication with a connected PC client using TCP"""
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

def send_data_to_phone_udp(server_socket, client_address, num_requests, interval_ms, bytes_per_request):
    """Send data packets to the phone client based on trigger packets using UDP"""
    try:
        print(f"Ready to send {num_requests} requests to {client_address} when triggered")
        
        requests_sent = 0
        
        while requests_sent < num_requests:
            try:
                # Wait for trigger packet from client
                trigger, addr = server_socket.recvfrom(MAX_UDP_SEGMENT)
                print(f"Received trigger from {addr}")
                
                # Verify client address matches
                if addr != client_address:
                    print(f"Received packet from unexpected client {addr}, expected {client_address}")
                    continue
                
                # Check if it's a valid trigger packet (we'll use 'TRIG' as the trigger)
                if trigger != b'TRIG':
                    print(f"Received invalid trigger packet: {trigger}")
                    continue
                    
                # Get current timestamp
                current_time = time.time()
                
                # Create payload of specified size with zeros
                payload = b''
                if bytes_per_request > 0:
                    payload = b'\x00' * bytes_per_request
                    
                # Generate a unique request ID for this request
                request_id = requests_sent + 1
                
                # Create header with request ID, timestamp, packet size, and total segments
                # Format: !IdII = 4-byte int (request ID) + 8-byte double + 4-byte unsigned int + 4-byte unsigned int = 20 bytes total
                total_segments = (bytes_per_request + MAX_UDP_SEGMENT - 1) // MAX_UDP_SEGMENT if bytes_per_request > 0 else 0
                header = struct.pack('!IdII', request_id, current_time, bytes_per_request, total_segments)
                
                # Send header
                server_socket.sendto(header, client_address)
                
                # Send payload in segments if needed
                if bytes_per_request > 0:
                    # Add request ID to each segment by prepending it
                    for i in range(0, bytes_per_request, MAX_UDP_SEGMENT - 4):  # Reserve 4 bytes for request ID
                        # Get the segment data
                        segment_data = payload[i:i+MAX_UDP_SEGMENT-4]
                        # Create segment with request ID + data
                        segment = struct.pack('!I', request_id) + segment_data
                        # Send segment
                        server_socket.sendto(segment, client_address)
                        time.sleep(0.0001)  # Sleep for 100 microseconds
                
                requests_sent += 1
                print(f"Sent request {request_id}/{num_requests} to {client_address}: {bytes_per_request} bytes of payload in {total_segments} segments")
            
            except Exception as e:
                print(f"Error sending data: {e}")
                continue
                
        print(f"Completed sending all {requests_sent}/{num_requests} requests to {client_address}")
        
    except Exception as e:
        print(f"Error sending data to phone client {client_address}: {e}")

def handle_phone_client_udp(server_socket, client_address, param_bytes):
    """Handle communication with a phone client over UDP"""
    try:
        if len(param_bytes) < 12:
            print(f"Received invalid parameters from {client_address}, size: {len(param_bytes)} bytes")
            return
        
        # Parse parameters
        try:
            num_requests, interval_ms, bytes_per_request = struct.unpack('!iii', param_bytes[:12])
            
            print(f"Received parameters from {client_address}:")
            print(f"  - Number of requests: {num_requests}")
            print(f"  - Interval: {interval_ms}ms (used for timing)")
            print(f"  - Bytes per request: {bytes_per_request}")
            
            # Send acknowledgment
            server_socket.sendto(b'ACK', client_address)
            
            # Process client requests (in the same thread for UDP)
            send_data_to_phone_udp(server_socket, client_address, num_requests, interval_ms, bytes_per_request)
            
        except struct.error as e:
            print(f"Invalid parameters received from {client_address}: {e}")
            server_socket.sendto(b'ERR', client_address)
            
    except Exception as e:
        print(f"Error handling phone client {client_address}: {e}")

def listen_for_pc_clients():
    """Listen for PC client connections on SERVER_SYNC_PORT using TCP"""
    # Create TCP socket for PC clients
    pc_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    pc_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Disable Nagle algorithm
    pc_server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    pc_server_socket.bind((SERVER_IP, SERVER_SYNC_PORT))
    pc_server_socket.listen(5)  # Allow up to 5 queued connections
    
    print(f"AWS Server listening for PC clients on TCP {SERVER_IP}:{SERVER_SYNC_PORT}")
    
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

def listen_for_phone_clients_udp():
    """Listen for phone client connections on PHONE_SERVER_PORT using UDP"""
    # Create UDP socket for phone clients
    phone_server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    phone_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    # Set large buffer size
    phone_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, UDP_BUFFER_SIZE)
    phone_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, UDP_BUFFER_SIZE)
    
    phone_server_socket.bind((SERVER_IP, PHONE_SERVER_PORT))
    
    print(f"AWS Server listening for phone clients on UDP {SERVER_IP}:{PHONE_SERVER_PORT}")
    
    try:
        # Continuously listen for new client parameters
        while True:
            try:
                # Receive parameters from a phone client
                param_bytes, client_address = phone_server_socket.recvfrom(MAX_UDP_SEGMENT)
                
                # Handle this client
                handle_phone_client_udp(phone_server_socket, client_address, param_bytes)
                
            except Exception as e:
                print(f"Error receiving client data: {e}")
                continue
    
    except KeyboardInterrupt:
        print("Phone server shutting down...")
    finally:
        phone_server_socket.close()

def main():
    # Start PC client listener thread (TCP)
    pc_thread = threading.Thread(target=listen_for_pc_clients)
    pc_thread.daemon = True
    pc_thread.start()
    
    # Start phone client listener thread (UDP)
    phone_thread = threading.Thread(target=listen_for_phone_clients_udp)
    phone_thread.daemon = True
    phone_thread.start()
    
    print(f"AWS Server running with TCP connections for PC clients and UDP for phone clients")
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Server shutting down...")

if __name__ == "__main__":
    main()
