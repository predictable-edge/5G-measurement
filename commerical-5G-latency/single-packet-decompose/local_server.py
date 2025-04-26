#!/usr/bin/env python3
import socket
import time
import struct
import threading
import select
import argparse  # Import argparse for command-line argument parsing
import os
import datetime

# Configuration
AWS_SERVER_PORT = 5000       # Port for timestamp service
PHONE_LISTEN_IP = '0.0.0.0'  # Listen on all interfaces for phone connection
PHONE_LISTEN_PORT = 5001     # Port for receiving data from phone
TIME_SYNC_INTERVAL = 1       # Sync time with AWS server every second

# Global variables
time_offset = 0.0            # Time difference between client and AWS server
last_sync_time = 0           # Last time we synced with AWS server
phone_data_lock = threading.Lock()  # Lock for thread-safe updates to data
aws_socket = None            # TCP connection to AWS server
measurement_count = 0        # Counter for measurements
results_file = None          # File to save results

def connect_to_aws_server(aws_server_ip):
    """Establish TCP connection to AWS server"""
    global aws_socket
    
    while True:
        try:
            # Create TCP socket
            aws_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Disable Nagle algorithm
            aws_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            aws_socket.connect((aws_server_ip, AWS_SERVER_PORT))
            print(f"Connected to AWS server at {aws_server_ip}:{AWS_SERVER_PORT}")
            return
        except Exception as e:
            print(f"Failed to connect to AWS server: {e}")
            print("Retrying in 5 seconds...")
            time.sleep(5)

def sync_with_aws_server(aws_server_ip):
    """Periodically sync time with AWS server"""
    global time_offset, last_sync_time, aws_socket
    
    while True:
        try:
            # Ensure we have a connection
            if aws_socket is None:
                connect_to_aws_server(aws_server_ip)
                
            send_time = time.time()
            
            # Send empty packet as request to AWS server
            aws_socket.sendall(b'x')  # Send a single byte as request
            
            # Receive response from AWS server
            data = aws_socket.recv(1024)
            if not data:
                # Connection closed, try to reconnect
                print("AWS server connection closed, reconnecting...")
                aws_socket.close()
                aws_socket = None
                connect_to_aws_server(aws_server_ip)
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
                
            print(f"Synced with AWS server - Offset: {offset:.6f}s, RTT: {rtt*1000:.2f}ms")
            
            # Wait for next sync interval
            time.sleep(TIME_SYNC_INTERVAL)
            
        except Exception as e:
            print(f"Error syncing with AWS server: {e}")
            # Close socket and try to reconnect next time
            if aws_socket:
                aws_socket.close()
                aws_socket = None
            time.sleep(1)  # Wait before retrying

def handle_phone_client(client_socket, client_address, results_file):
    """Handle a phone client connection"""
    global measurement_count
    
    try:
        print(f"Phone connected from {client_address}")
        
        while True:
            # Receive data from phone
            data = client_socket.recv(1024)
            if not data:
                # Connection closed by phone
                break
                
            # Record reception time
            receive_time = time.time()
            
            # Unpack received data: server_timestamp, rtt, phone_receive_time
            server_timestamp, phone_rtt, phone_receive_time = struct.unpack('ddd', data)
            
            with phone_data_lock:
                # Apply our time offset to convert to local time
                corrected_server_time = server_timestamp - time_offset
                
                # Calculate DL delay (server to phone)
                dl_delay = receive_time - corrected_server_time
                
                # Calculate UL delay (phone to server)
                ul_delay = phone_rtt - dl_delay
                
                # Increment measurement counter
                measurement_count += 1
                
                # Save results to file with fixed-width format for better alignment (left-aligned)
                results_file.write(f"{measurement_count:<6d}  {phone_rtt*1000:<10.2f}  {ul_delay*1000:<10.2f}  {dl_delay*1000:<10.2f}\n")
                results_file.flush()  # Ensure data is written to disk
            
            print(f"Data from phone: RTT={phone_rtt*1000:.2f}ms")
            print(f"Calculated delays - DL: {dl_delay*1000:.2f}ms, UL: {ul_delay*1000:.2f}ms")
            print(f"Saved measurement #{measurement_count} to file")
    
    except Exception as e:
        print(f"Error handling phone client {client_address}: {e}")
    finally:
        # Close the connection
        client_socket.close()
        print(f"Phone connection closed with {client_address}")

def listen_for_phone(results_file):
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
        while True:
            # Accept new connection
            client_socket, client_address = phone_socket.accept()
            
            # Start a new thread to handle this client
            client_thread = threading.Thread(
                target=handle_phone_client,
                args=(client_socket, client_address, results_file)
            )
            client_thread.daemon = True
            client_thread.start()
    
    except KeyboardInterrupt:
        print("Phone listener shutting down...")
    finally:
        phone_socket.close()

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Local server for latency decomposition')
    parser.add_argument('--aws-ip', dest='aws_server_ip', required=True,
                        help='IP address of the AWS server')
    args = parser.parse_args()
    
    # Create timestamp for filename
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create results file
    results_filename = f"aws_latency_{timestamp}.txt"
    results_file = open(results_filename, "w")
    
    # Write header to results file with fixed-width format (left-aligned)
    results_file.write(f"{'index':<6s}  {'rtt_ms':<10s}  {'ul_ms':<10s}  {'dl_ms':<10s}\n")
    
    print(f"Saving results to {results_filename}")
    
    try:
        # Connect to AWS server
        connect_to_aws_server(args.aws_server_ip)
        
        # Start thread for AWS server time sync
        aws_sync_thread = threading.Thread(target=sync_with_aws_server, args=(args.aws_server_ip,), daemon=True)
        aws_sync_thread.start()
        
        # Start thread for listening for phone connections
        phone_listen_thread = threading.Thread(target=listen_for_phone, args=(results_file,), daemon=True)
        phone_listen_thread.start()
        
        # Keep the main thread running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Exiting...")
            if aws_socket:
                aws_socket.close()
    finally:
        # Close results file
        if results_file:
            results_file.close()
            print(f"Results saved to {results_filename}")

if __name__ == "__main__":
    main()