#!/usr/bin/env python3
import socket
import time
import struct
import threading
import datetime

# Configuration
SERVER_IP = '0.0.0.0'  # Listen on all interfaces
SERVER_SYNC_PORT = 5000     # Port for timestamp service (TCP)
PHONE_UDP_PORT = 5002       # Port for receiving data from phone client (UDP)
MAX_UDP_SEGMENT = 1300      # Maximum UDP segment size
UDP_BUFFER_SIZE = 4194304   # Buffer size for UDP socket (4MB)
PING_PONG_PORT = 5001       # Port for UDP ping-pong measurements

# Global variables
running = True              # Flag to control thread execution
results_file = None         # File to save results
results_filename = None     # Filename for results
is_file_created = False     # Flag to indicate if results file is created
expected_bytes_size = 0     # Size of data packets for filename
result_counter = 0          # Counter for sequential result indices

# Data structures for UDP requests from phone client
pending_requests = {}       # Dictionary to track requests that are being processed
completed_requests = {}     # Dictionary to store timing info for completed requests
request_lock = threading.Lock()  # Lock for thread-safe access to request dictionaries

def init_results_file(payload_size):
    """Initialize the results file with headers"""
    global results_file, results_filename, is_file_created, expected_bytes_size
    
    # Don't create the file again if it's already created
    if is_file_created:
        return
        
    try:
        # Store the payload size for future reference
        expected_bytes_size = payload_size
        
        # Create a timestamp for the filename
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        results_filename = f"ul_udp_bytes{payload_size}_{timestamp}.txt"
        
        results_file = open(results_filename, "w")
        results_file.write(f"{'index':<6s}  {'ul_delay_ms':<12s}  {'duration_ms':<12s}  {'packet_size':<10s}  {'sync_rtt_ms':<10s}\n")
        results_file.flush()
        print(f"Results file initialized: {results_filename}")
        is_file_created = True
    except Exception as e:
        print(f"Error initializing results file: {e}")
        results_file = None

def save_request_result(transmission_delay_ms, total_transfer_time_ms, packet_size, rtt_ms):
    """Save a request result to the results file using a sequential index"""
    global results_file, result_counter
    
    if results_file is None:
        return
    
    try:
        # Increment the result counter
        result_counter += 1
        
        # Write formatted result to file using the counter as index
        results_file.write(f"{result_counter:<6d}  {transmission_delay_ms:<12.2f}  {total_transfer_time_ms:<12.2f}  {packet_size:<10d}  {rtt_ms:<10.2f}\n")
        results_file.flush()
    except Exception as e:
        print(f"Error saving result to file: {e}")

def handle_pc_client(client_socket, client_address):
    """Handle communication with a connected PC client using TCP for time synchronization"""
    try:
        print(f"New PC connection from {client_address}")
        
        while True:
            # Receive request from PC
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

def handle_phone_udp_data():
    """Listen for UDP data from phone client and track timing information"""
    global running, pending_requests, completed_requests, is_file_created
    
    # Create UDP socket
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    # Set large buffer size
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, UDP_BUFFER_SIZE)
    
    # Bind to port
    udp_socket.bind((SERVER_IP, PHONE_UDP_PORT))
    
    print(f"UDP listener started on {SERVER_IP}:{PHONE_UDP_PORT}")
    
    try:
        while running:
            try:
                # Receive data from phone client
                data, addr = udp_socket.recvfrom(MAX_UDP_SEGMENT)
                
                # Check if this is a header or a data segment
                # Header format: request_id (4) + timestamp (8) + size (4) + offset (8) + sync_rtt (8) = 32 bytes
                if len(data) >= 32 and len(data) <= 36:  # Header (32-36 bytes with potential padding)
                    try:
                        # Parse header data with offset and sync RTT
                        request_id, client_timestamp, expected_payload_size, time_offset, sync_rtt = struct.unpack('!IdIdd', data[:32])
                        
                        # Initialize results file if not done yet
                        if not is_file_created:
                            init_results_file(expected_payload_size)
                        
                        # Record reception time
                        header_recv_time = time.time()
                        
                        # Calculate transmission delay using PC's time offset and sync RTT
                        # PC has already adjusted the timestamp, so we can use it directly
                        corrected_client_timestamp = client_timestamp + time_offset
                        transmission_delay = header_recv_time - corrected_client_timestamp
                        
                        # Store the request info
                        with request_lock:
                            pending_requests[request_id] = {
                                'header_recv_time': header_recv_time,
                                'client_timestamp': client_timestamp,
                                'corrected_timestamp': corrected_client_timestamp,
                                'transmission_delay': transmission_delay,
                                'expected_size': expected_payload_size,
                                'sync_rtt': sync_rtt,
                                'segments_received': 0,
                                'total_bytes_received': 0
                            }
                        
                        print(f"Header received from {addr} - Request ID: {request_id}, "
                              f"Transmission delay: {transmission_delay*1000:.2f}ms, "
                              f"Expected size: {expected_payload_size} bytes, "
                              f"Sync RTT: {sync_rtt*1000:.2f}ms")
                        
                        # If no payload expected, process immediately
                        if expected_payload_size == 0:
                            with request_lock:
                                if request_id in pending_requests:
                                    req_info = pending_requests[request_id]
                                    total_transfer_time = 0  # No payload transfer
                                    
                                    # Save result
                                    save_request_result(
                                        req_info['transmission_delay'] * 1000,  # Convert to ms
                                        total_transfer_time,
                                        expected_payload_size,
                                        req_info['sync_rtt'] * 1000  # Convert to ms
                                    )
                                    
                                    # Move to completed requests
                                    completed_requests[request_id] = req_info
                                    del pending_requests[request_id]
                                    
                                    print(f"Request {request_id} completed (no payload)")
                    
                    except struct.error as e:
                        print(f"Error parsing header from {addr}: {e}")
                        continue
                elif len(data) >= 4:  # Data segment (at least 4 bytes for request_id)
                    try:
                        # Extract request ID
                        request_id = struct.unpack('!I', data[:4])[0]
                        
                        # Get segment data (excluding request ID)
                        segment_data = data[4:]
                        segment_size = len(segment_data)
                        
                        with request_lock:
                            # Check if we have this request in our pending list
                            if request_id in pending_requests:
                                request = pending_requests[request_id]
                                
                                # Update segment count and total bytes
                                request['segments_received'] += 1
                                request['total_bytes_received'] += segment_size
                                
                                # Record first segment time
                                if request['segments_received'] == 1:
                                    request['first_segment_time'] = time.time()
                                
                                # Always update the last segment time
                                request['last_segment_time'] = time.time()
                                
                                # Print progress every few segments
                                if request['segments_received'] % 10 == 0:
                                    print(f"Received segment {request['segments_received']} for request ID {request_id}, total bytes: {request['total_bytes_received']}/{request['expected_size']}")
                                
                                # Check if we've received all expected data
                                if request['total_bytes_received'] >= request['expected_size'] and request['expected_size'] > 0:
                                    print(f"Received all expected data for request ID {request_id} ({request['total_bytes_received']}/{request['expected_size']} bytes)")
                                    
                                    # Calculate timing information
                                    transmission_delay_ms = request['transmission_delay'] * 1000
                                    
                                    if 'first_segment_time' in request:
                                        first_segment_delay = request['first_segment_time'] - request['corrected_timestamp']
                                        first_segment_delay_ms = first_segment_delay * 1000
                                    else:
                                        first_segment_delay_ms = 0
                                        
                                    total_transfer_time = request['last_segment_time'] - request['header_recv_time']
                                    total_transfer_time_ms = total_transfer_time * 1000
                                    
                                    # Get the RTT used for this request
                                    rtt_ms = request['sync_rtt'] * 1000
                                    
                                    # Print completion info
                                    print("--------------------------------")
                                    print(f"Request ID {request_id} completed:")
                                    print(f"  Segments received: {request['segments_received']}")
                                    print(f"  Total bytes: {request['total_bytes_received']}")
                                    print(f"  Transmission delay: {transmission_delay_ms:.2f} ms")
                                    print(f"  First segment delay: {first_segment_delay_ms:.2f} ms")
                                    print(f"  Total transfer time: {total_transfer_time_ms:.2f} ms")
                                    print(f"  Sync RTT: {rtt_ms:.2f} ms")
                                    print("--------------------------------")
                                    
                                    # Save results to file
                                    save_request_result(
                                        transmission_delay_ms,
                                        total_transfer_time_ms,
                                        request['total_bytes_received'],
                                        rtt_ms
                                    )
                                    
                                    # Move to completed requests
                                    completed_requests[request_id] = request.copy()
                                    del pending_requests[request_id]
                            else:
                                print(f"Received segment for unknown request ID {request_id} from {addr}")
                    except struct.error:
                        print(f"Invalid segment format from {addr}")
                        continue
                else:
                    # Skip unrecognized packet sizes
                    print(f"Received packet with unexpected size {len(data)} bytes from {addr}")
            except Exception as e:
                print(f"Error handling UDP data: {e}")
                continue
    
    except Exception as e:
        print(f"Error in UDP listener: {e}")
    finally:
        udp_socket.close()
        print("UDP listener stopped")

def handle_ping_pong_udp():
    """
    Handle ping-pong requests over UDP.
    Immediately responds to each ping message with a pong message.
    """
    try:
        # Create UDP socket for ping-pong
        ping_pong_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        ping_pong_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ping_pong_socket.bind((SERVER_IP, PING_PONG_PORT))
        
        print(f"Server listening for ping-pong requests on UDP {SERVER_IP}:{PING_PONG_PORT}")
        
        pong_count = 0
        
        while running:
            # Receive ping request
            data, client_address = ping_pong_socket.recvfrom(1024)
            
            try:
                message = data.decode()
                
                # Handle PING message
                if message.startswith("PING:"):
                    # Extract sequence number
                    sequence = message.split(":")[1]
                    
                    # Create pong response with same sequence
                    response = f"PONG:{sequence}".encode()
                    
                    # Send response back to the client (same address that sent the ping)
                    ping_pong_socket.sendto(response, client_address)
                    
                    pong_count += 1
                    if pong_count % 100 == 0:
                        print(f"Sent {pong_count} pong responses")
                else:
                    print(f"Unexpected message format from {client_address}: {message}")
            
            except Exception as e:
                print(f"Error processing ping-pong message: {e}")
                continue
    
    except Exception as e:
        print(f"Error in ping-pong UDP handler: {e}")
    finally:
        if 'ping_pong_socket' in locals():
            ping_pong_socket.close()

def listen_for_clients():
    """Listen for client connections on SERVER_SYNC_PORT using TCP"""
    # Create TCP socket for clients
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Disable Nagle algorithm
    server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    server_socket.bind((SERVER_IP, SERVER_SYNC_PORT))
    server_socket.listen(5)  # Allow multiple connections
    
    print(f"Server listening for clients on TCP {SERVER_IP}:{SERVER_SYNC_PORT}")
    
    try:
        while running:
            # Accept new connection (old connection will be closed if a new one comes in)
            client_sock, client_address = server_socket.accept()
            # Disable Nagle algorithm for the client socket too
            client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            # Handle this client in a new thread
            client_thread = threading.Thread(
                target=handle_pc_client,
                args=(client_sock, client_address)
            )
            client_thread.daemon = True
            client_thread.start()
    
    except KeyboardInterrupt:
        print("Server shutting down...")
    finally:
        server_socket.close()

def main():
    global running, results_file, result_counter, is_file_created
    
    # Reset result counter
    result_counter = 0
    
    # File will be created on first valid packet
    is_file_created = False
    
    # Start client listener thread (TCP)
    client_thread = threading.Thread(target=listen_for_clients)
    client_thread.daemon = True
    client_thread.start()
    
    # Start UDP listener thread for phone client data
    udp_thread = threading.Thread(target=handle_phone_udp_data)
    udp_thread.daemon = True
    udp_thread.start()

    # Start ping-pong handler thread (UDP)
    ping_pong_thread = threading.Thread(target=handle_ping_pong_udp)
    ping_pong_thread.daemon = True
    ping_pong_thread.start()
    
    print(f"Server running and responding to PC-initiated time synchronization requests")
    print(f"Time offset and sync RTT are calculated and stored on PC side")
    print(f"UDP listener active on port {PHONE_UDP_PORT} for phone client data")
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Server shutting down...")
        running = False
        
        # Close results file
        if results_file:
            results_file.close()
            if results_filename:
                print(f"Results saved to {results_filename}")

if __name__ == "__main__":
    main()
