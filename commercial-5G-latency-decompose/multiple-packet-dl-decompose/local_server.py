#!/usr/bin/env python3
import socket
import time
import struct
import threading
import argparse
import datetime
import os

# Configuration
AWS_SERVER_IP_PORT = 5000       # Port for timestamp service
PHONE_LISTEN_IP = '0.0.0.0'     # Listen on all interfaces for phone connection
PHONE_LISTEN_PORT = 5001        # Port for receiving data from phone
TIME_SYNC_INTERVAL = 1          # Sync time with AWS server every second

# Global variables
time_offset = 0.0               # Time difference between client and AWS server
last_sync_time = 0              # Last time we synced with AWS server
aws_time_socket = None          # TCP connection to AWS server for time sync
phone_data_lock = threading.Lock()  # Lock for thread-safe updates to data
running = True                  # Flag to control thread execution
measurement_count = 0           # Counter for received packets
results_file = None             # File to save measurement results
results_filename = None         # Filename for results
is_file_created = False         # Flag to indicate if results file is created
current_sync_rtt = 0.0          # Current RTT with AWS time server

def connect_to_aws_time_server(aws_server_ip):
    """Establish TCP connection to AWS server for time synchronization"""
    global aws_time_socket
    
    while True:
        try:
            # Create TCP socket
            aws_time_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Disable Nagle algorithm
            aws_time_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            aws_time_socket.connect((aws_server_ip, AWS_SERVER_IP_PORT))
            print(f"Connected to AWS time server at {aws_server_ip}:{AWS_SERVER_IP_PORT}")
            return
        except Exception as e:
            print(f"Failed to connect to AWS time server: {e}")
            print("Retrying in 5 seconds...")
            time.sleep(5)

def sync_with_aws_server(aws_server_ip):
    """Periodically sync time with AWS server"""
    global time_offset, last_sync_time, aws_time_socket, running, current_sync_rtt
    
    while running:
        try:
            # Ensure we have a connection
            if aws_time_socket is None:
                connect_to_aws_time_server(aws_server_ip)
                
            send_time = time.time()
            
            # Send empty packet as request to AWS server
            aws_time_socket.sendall(b'x')  # Send a single byte as request
            
            # Receive response from AWS server
            data = aws_time_socket.recv(1024)
            if not data:
                # Connection closed, try to reconnect
                print("AWS server connection closed, reconnecting...")
                aws_time_socket.close()
                aws_time_socket = None
                connect_to_aws_time_server(aws_server_ip)
                continue
                
            receive_time = time.time()
            
            # Unpack timestamp from response
            server_time = struct.unpack('d', data)[0]
            rtt = receive_time - send_time
            
            # Calculate one-way delay (assuming symmetric network)
            one_way_delay = rtt / 2
            
            # Calculate time offset (difference between our time and server time)
            # Adjusted for the one-way delay
            offset = server_time - (send_time + one_way_delay)
            
            with phone_data_lock:
                time_offset = offset
                last_sync_time = time.time()
                current_sync_rtt = rtt  # Store the latest RTT value
                
            print(f"Synced with AWS server - Offset: {offset:.6f}s, RTT: {rtt*1000:.2f}ms")
            
            # Wait for next sync interval
            time.sleep(TIME_SYNC_INTERVAL)
            
        except Exception as e:
            print(f"Error syncing with AWS server: {e}")
            # Close socket and try to reconnect next time
            if aws_time_socket:
                aws_time_socket.close()
                aws_time_socket = None
            time.sleep(1)  # Wait before retrying

def handle_phone_client(client_socket, client_address):
    """Handle a phone client connection"""
    global measurement_count, results_file, current_sync_rtt, is_file_created, results_filename
    
    try:
        print(f"Phone connected from {client_address}")
        
        # Set socket to non-blocking mode with minimal read delay
        client_socket.setblocking(False)
        
        # Track what kind of data we expect next
        expected_data = "header"  # We first expect a header
        
        while running:
            try:
                # Try to receive data
                start_recv = time.time()
                data = client_socket.recv(20)  # Now expect 20 bytes instead of 12
                end_recv = time.time()
                if not data:
                    print("Connection closed by phone")
                    break
                
                recv_delay = (end_recv - start_recv) * 1000
                print(f"Received data length: {len(data)}, recv delay: {recv_delay:.3f} ms")
                
                # Process the received data based on what we expect
                if expected_data == "header" and len(data) == 20:  # Changed from 12 to 20
                    # We have a complete header
                    # Record reception time of the header
                    header_recv_time = time.time()
                    print(f"header_recv_time: {header_recv_time}")
                    
                    # Parse the header to get timestamp, packet size, and phone time difference
                    server_timestamp, packet_size, phone_time_diff_ms = struct.unpack('!dId', data)
                    
                    # Calculate local time difference
                    local_time_diff_ms = (header_recv_time - server_timestamp) * 1000
                    
                    # Create results file if this is the first packet with valid size
                    if not is_file_created and packet_size >= 0:
                        create_results_file(packet_size)
                        is_file_created = True
                    
                    # Correct the server timestamp using our time offset
                    with phone_data_lock:
                        corrected_server_time = server_timestamp - time_offset
                        sync_rtt = current_sync_rtt  # Get current sync RTT value
                    
                    # Calculate DL transmission delay (server to phone)
                    dl_transmission_delay = header_recv_time - corrected_server_time
                    
                    print(f"Header received from phone. Server timestamp: {server_timestamp:.6f}")
                    print(f"Corrected server time: {corrected_server_time:.6f}")
                    print(f"DL transmission delay: {dl_transmission_delay*1000:.2f} ms")
                    print(f"Phone time difference: {phone_time_diff_ms:.2f} ms")
                    print(f"Local time difference: {local_time_diff_ms:.2f} ms")
                    print(f"Current sync RTT: {sync_rtt*1000:.2f} ms")
                    
                    # Now expect duration data
                    expected_data = "duration"
                
                elif expected_data == "header" and len(data) == 8:
                    # We expect header but have 8 bytes (possibly duration data)
                    # This might be an out-of-sequence duration data
                    print("Warning: Received unexpected 8-byte data while expecting header, discarding")
                    # Just discard and continue expecting header
                    
                elif expected_data == "duration" and len(data) == 8:
                    # We have duration data
                    # Parse the duration data
                    duration_ms = struct.unpack('d', data)[0]
                    
                    # Calculate total latency
                    total_latency_ms = dl_transmission_delay*1000 + duration_ms
                    
                    # Increment measurement counter
                    measurement_count += 1
                    
                    # Save results to file with fixed-width format for better alignment
                    if results_file:
                        with phone_data_lock:  # Use lock to avoid file corruption
                            results_file.write(f"{measurement_count:<6d}  {dl_transmission_delay*1000:<12.2f}  {phone_time_diff_ms:<14.2f}  {local_time_diff_ms:<14.2f}  {duration_ms:<12.2f}  {total_latency_ms:<12.2f}  {packet_size:<10d}  {sync_rtt*1000:<10.2f}\n")
                            results_file.flush()  # Ensure data is written to disk
                    
                    print(f"Packet reception duration on phone: {duration_ms:.2f} ms")
                    print(f"Total observed latency: {total_latency_ms:.2f} ms")
                    print(f"Saved measurement #{measurement_count} to file")
                    print("-" * 50)
                    
                    # Now expect a new header
                    expected_data = "header"
                
                elif expected_data == "duration" and len(data) == 20:  # Changed from 12 to 20
                    # We didn't get duration data, but we got another header
                    # This means the phone skipped sending duration
                    print("Warning: Missing duration data, received new header instead")
                    
                    # Process this as a header
                    header_recv_time = time.time()
                    server_timestamp, packet_size, phone_time_diff_ms = struct.unpack('!dId', data)
                    
                    # Calculate local time difference
                    local_time_diff_ms = (header_recv_time - server_timestamp) * 1000
                    
                    with phone_data_lock:
                        corrected_server_time = server_timestamp - time_offset
                        sync_rtt = current_sync_rtt
                    
                    dl_transmission_delay = header_recv_time - corrected_server_time
                    
                    print(f"Time difference: {header_recv_time - server_timestamp}")
                    print(f"Header received from phone. Server timestamp: {server_timestamp:.6f}")
                    print(f"Corrected server time: {corrected_server_time:.6f}")
                    print(f"DL transmission delay: {dl_transmission_delay*1000:.2f} ms")
                    print(f"Phone time difference: {phone_time_diff_ms:.2f} ms") 
                    print(f"Local time difference: {local_time_diff_ms:.2f} ms")
                    print(f"Current sync RTT: {sync_rtt*1000:.2f} ms")
                    
                    # Continue expecting duration data for this new header
                    expected_data = "duration"
                    
                else:
                    print(f"Received data with unexpected length: {len(data)} bytes while expecting {expected_data}")
                    
            except BlockingIOError:
                continue
            except Exception as e:
                print(f"Error receiving data: {e}")
                break
    
    except Exception as e:
        print(f"Error handling phone client {client_address}: {e}")
    finally:
        # Close the connection
        client_socket.close()
        print(f"Phone connection closed with {client_address}")

def listen_for_phone():
    """Listen for phone connections"""
    # Create TCP socket for phone communication
    phone_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    phone_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Disable Nagle algorithm
    phone_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    phone_socket.bind((PHONE_LISTEN_IP, PHONE_LISTEN_PORT))
    phone_socket.listen(5)  # Allow up to 5 queued connections
    
    print(f"Listening for phone connections on {PHONE_LISTEN_IP}:{PHONE_LISTEN_PORT}")
    
    try:
        while running:
            try:
                # Accept new connection
                client_socket, client_address = phone_socket.accept()
                # Explicitly disable Nagle algorithm for the client socket too
                client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                # Enable TCP_QUICKACK for Linux systems
                try:
                    client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_QUICKACK, 1)
                except AttributeError:
                    # TCP_QUICKACK not available on all platforms
                    pass
                
                # Set small buffer sizes to reduce latency
                try:
                    # Use smaller TCP buffer to reduce latency (8KB)
                    client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8192)
                    cur_rcvbuf = client_socket.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
                    print(f"TCP receive buffer size set to: {cur_rcvbuf} bytes")
                except Exception as e:
                    print(f"Could not set TCP buffer size: {e}")
                
                # Start a new thread to handle this client
                client_thread = threading.Thread(
                    target=handle_phone_client,
                    args=(client_socket, client_address)
                )
                client_thread.daemon = True
                client_thread.start()
            except socket.timeout:
                # Socket timeout, just continue the loop
                continue
            except Exception as e:
                if running:  # Only log error if we're still supposed to be running
                    print(f"Error accepting connection: {e}")
                    time.sleep(1)  # Avoid tight loop if there's an error
    
    except Exception as e:
        print(f"Error in phone listener: {e}")
    finally:
        phone_socket.close()
        print("Phone listener shut down")

def create_results_file(packet_size):
    """Create results file with packet size in the filename"""
    global results_file, results_filename
    
    # Create timestamp for filename
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create results file with packet size in the filename
    results_filename = f"udp_latency_bytes{packet_size}_{timestamp}.txt"
    results_file = open(results_filename, "w")
    
    # Write header to results file with fixed-width format
    results_file.write(f"{'index':<6s}  {'dl_delay_ms':<12s}  {'phone_diff_ms':<14s}  {'local_diff_ms':<14s}  {'duration_ms':<12s}  {'total_ms':<12s}  {'packet_size':<10s}  {'sync_rtt_ms':<10s}\n")
    results_file.write("-" * 90 + "\n")
    
    print(f"Saving results to {results_filename}")

def main():
    global aws_time_socket, running, results_file
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Time synchronization client for AWS server')
    parser.add_argument('--aws-ip', dest='aws_server_ip', required=True,
                        help='IP address of the AWS server')
    parser.add_argument('--interval', type=float, default=1.0,
                        help='Time sync interval in seconds (default: 1.0)')
    args = parser.parse_args()
    
    # Update sync interval if specified
    global TIME_SYNC_INTERVAL
    TIME_SYNC_INTERVAL = args.interval
    
    try:
        # Connect to AWS server for time synchronization
        connect_to_aws_time_server(args.aws_server_ip)
        
        # Start thread for AWS server time sync
        aws_sync_thread = threading.Thread(
            target=sync_with_aws_server, 
            args=(args.aws_server_ip,), 
            daemon=True
        )
        aws_sync_thread.start()
        
        # Start thread for listening for phone connections
        phone_listen_thread = threading.Thread(
            target=listen_for_phone, 
            daemon=True
        )
        phone_listen_thread.start()
        
        print(f"Time sync client running with interval {TIME_SYNC_INTERVAL}s")
        print(f"Phone listener running on port {PHONE_LISTEN_PORT}")
        print("Press Ctrl+C to exit")
        
        # Keep the main thread running
        try:
            while running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("Exiting...")
            running = False
    finally:
        # Close connections
        if aws_time_socket:
            aws_time_socket.close()
        
        # Close results file
        if results_file:
            results_file.close()
            if results_filename:
                print(f"Results saved to {results_filename}")

if __name__ == "__main__":
    main()
