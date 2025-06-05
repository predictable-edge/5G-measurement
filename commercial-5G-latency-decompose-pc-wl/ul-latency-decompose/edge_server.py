#!/usr/bin/env python3
import socket
import time
import struct
import threading
import datetime

# Configuration
SERVER_IP = '0.0.0.0'           # Listen on all interfaces
PHONE_UDP_PORT = 5002           # Port for receiving data from phone client (UDP)
MAX_UDP_SEGMENT = 1300          # Maximum UDP segment size
UDP_BUFFER_SIZE = 4194304       # Buffer size for UDP socket (4MB)
PING_PONG_PORT = 5001           # Port for UDP ping-pong measurements

# Global variables
running = True                  # Flag to control thread execution
results_file = None             # File to save results
results_filename = None         # Filename for results
is_file_created = False         # Flag to indicate if results file is created
expected_bytes_size = 0         # Size of data packets for filename
result_counter = 0              # Counter for sequential result indices

# Data structures for UDP requests from phone client
pending_requests = {}           # Dictionary to track requests that are being processed
completed_requests = {}         # Dictionary to store timing info for completed requests
request_lock = threading.Lock() # Lock for thread-safe access to request dictionaries

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

def save_request_result(transmission_delay_ms, total_transfer_time_ms, packet_size, sync_rtt_ms):
    """Save a request result to the results file using a sequential index"""
    global results_file, result_counter
    
    if results_file is None:
        return
    
    try:
        # Increment the result counter
        result_counter += 1
        
        # Write formatted result to file using the counter as index
        results_file.write(f"{result_counter:<6d}  {transmission_delay_ms:<12.2f}  {total_transfer_time_ms:<12.2f}  {packet_size:<10d}  {sync_rtt_ms:<10.2f}\n")
        results_file.flush()
    except Exception as e:
        print(f"Error saving result to file: {e}")

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
                if len(data) >= 20 and len(data) <= 24:  # Header (20-24 bytes: request_id + timestamp + optional size + optional sync_rtt)
                    try:
                        # Parse header data - try new format first (24 bytes with sync_rtt)
                        if len(data) >= 24:
                            request_id, server_timestamp, expected_payload_size, sync_rtt = struct.unpack('!IdId', data[:24])
                        else:
                            # Fallback to old format (20 bytes without sync_rtt)
                            request_id, server_timestamp, expected_payload_size = struct.unpack('!IdI', data[:20])
                            sync_rtt = 0.0  # Default value for backward compatibility
                        
                        # Initialize results file if it hasn't been created yet and we have a valid payload size
                        if not is_file_created and expected_payload_size >= 0:
                            init_results_file(expected_payload_size)
                        
                        # Record reception time
                        header_recv_time = time.time()
                        
                        # Calculate transmission delay (no time offset correction needed now)
                        transmission_delay = header_recv_time - server_timestamp
                        
                        with request_lock:
                            # Store request info
                            pending_requests[request_id] = {
                                'server_time': server_timestamp,
                                'header_recv_time': header_recv_time,
                                'transmission_delay': transmission_delay,
                                'expected_payload_size': expected_payload_size,
                                'sync_rtt': sync_rtt,
                                'segments_received': 0,
                                'total_bytes': 0,
                                'is_complete': False,
                                'sender': addr
                            }
                        
                        print(f"Request ID: {request_id}, Expected payload size: {expected_payload_size} bytes, Sync RTT: {sync_rtt*1000:.2f}ms")
                        
                        # If expected payload size is 0, mark the request as complete immediately
                        if expected_payload_size == 0:
                            with request_lock:
                                if request_id in pending_requests:
                                    request = pending_requests[request_id]
                                    current_time = time.time()
                                    
                                    # Calculate timing information
                                    transmission_delay_ms = request['transmission_delay'] * 1000
                                    first_segment_delay_ms = 0  # No segments
                                    total_transfer_time_ms = 0  # No transfer time
                                    sync_rtt_ms = request['sync_rtt'] * 1000
                                    
                                    # Mark as complete
                                    request['is_complete'] = True
                                    request['completion_time'] = current_time
                                    
                                    # Print completion info immediately
                                    print("--------------------------------")
                                    print(f"Request ID {request_id} completed:")
                                    print(f"  Segments received: {request['segments_received']}")
                                    print(f"  Total bytes: {request['total_bytes']}")
                                    print(f"  Transmission delay: {transmission_delay_ms:.2f} ms")
                                    print(f"  First segment delay: {first_segment_delay_ms:.2f} ms")
                                    print(f"  Total transfer time: {total_transfer_time_ms:.2f} ms")
                                    print(f"  Sync RTT: {sync_rtt_ms:.2f} ms")
                                    print("--------------------------------")
                                    
                                    # Save results to file
                                    save_request_result(
                                        transmission_delay_ms,
                                        total_transfer_time_ms,
                                        request['total_bytes'],
                                        sync_rtt_ms
                                    )
                                    
                                    # Move to completed requests
                                    completed_requests[request_id] = request.copy()
                                    del pending_requests[request_id]
                        
                    except struct.error:
                        print(f"Invalid header format from {addr}")
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
                                
                                # Check if the sender matches
                                if request['sender'] != addr:
                                    print(f"Segment from {addr} has request ID {request_id} but different sender than original")
                                    continue
                                
                                # Update segment count and total bytes
                                request['segments_received'] += 1
                                request['total_bytes'] += segment_size
                                
                                # Always update the last segment time
                                request['last_segment_time'] = time.time()
                                
                                # Print progress every few segments
                                if request['segments_received'] % 10 == 0:
                                    print(f"Received segment {request['segments_received']} for request ID {request_id}, total bytes: {request['total_bytes']}/{request['expected_payload_size']}")
                                
                                # Check if we've received all expected data
                                if request['total_bytes'] >= request['expected_payload_size'] and request['expected_payload_size'] > 0:
                                    print(f"Received all expected data for request ID {request_id} ({request['total_bytes']}/{request['expected_payload_size']} bytes)")
                                    # Use direct call instead of function to avoid possible issues
                                    current_time = time.time()
                                    
                                    # Calculate timing information
                                    transmission_delay_ms = request['transmission_delay'] * 1000
                                    
                                    if 'first_segment_time' in request:
                                        first_segment_delay = request['first_segment_time'] - request['server_time']
                                        first_segment_delay_ms = first_segment_delay * 1000
                                    else:
                                        first_segment_delay_ms = 0
                                        
                                    total_transfer_time = request['last_segment_time'] - request['header_recv_time']
                                    total_transfer_time_ms = total_transfer_time * 1000
                                    sync_rtt_ms = request['sync_rtt'] * 1000
                                    
                                    # Mark as complete
                                    request['is_complete'] = True
                                    request['completion_time'] = current_time
                                    
                                    # Print completion info immediately while we still have the lock
                                    print("--------------------------------")
                                    print(f"Request ID {request_id} completed:")
                                    print(f"  Segments received: {request['segments_received']}")
                                    print(f"  Total bytes: {request['total_bytes']}")
                                    print(f"  Transmission delay: {transmission_delay_ms:.2f} ms")
                                    print(f"  First segment delay: {first_segment_delay_ms:.2f} ms")
                                    print(f"  Total transfer time: {total_transfer_time_ms:.2f} ms")
                                    print(f"  Sync RTT: {sync_rtt_ms:.2f} ms")
                                    print("--------------------------------")
                                    
                                    # Save results to file
                                    save_request_result(
                                        transmission_delay_ms,
                                        total_transfer_time_ms,
                                        request['total_bytes'],
                                        sync_rtt_ms
                                    )
                                    
                                    # Move to completed requests
                                    completed_requests[request_id] = request.copy()
                                    del pending_requests[request_id]
                            else:
                                print(f"Received segment for unknown request ID {request_id} from {addr}")
                    except struct.error:
                        print(f"Invalid segment format from {addr}")
                        continue
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

def main():
    global running, results_file, result_counter, is_file_created
    
    # Reset result counter
    result_counter = 0
    
    # File will be created on first valid packet
    is_file_created = False
    
    # Start UDP listener thread for phone client data
    udp_thread = threading.Thread(target=handle_phone_udp_data)
    udp_thread.daemon = True
    udp_thread.start()

    # Start ping-pong handler thread (UDP)
    ping_pong_thread = threading.Thread(target=handle_ping_pong_udp)
    ping_pong_thread.daemon = True
    ping_pong_thread.start()
    
    print(f"Edge server running - ready to receive data and handle ping-pong requests")
    print(f"UDP data listener active on port {PHONE_UDP_PORT} for phone client data")
    print(f"Ping-pong handler active on port {PING_PONG_PORT}")
    print("Note: Time synchronization functionality has been moved to lz_server.py")
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Edge server shutting down...")
        running = False
        
        # Close results file
        if results_file:
            results_file.close()
            if results_filename:
                print(f"Results saved to {results_filename}")

if __name__ == "__main__":
    main()
