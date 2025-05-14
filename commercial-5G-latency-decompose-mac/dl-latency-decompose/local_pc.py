#!/usr/bin/env python3
import socket
import time
import struct
import threading
import argparse

# Configuration
AWS_SERVER_IP_PORT = 5000       # Port for timestamp service
TIME_SYNC_INTERVAL = 1          # Sync time with AWS server every second

# Global variables
time_offset = 0.0               # Time difference between client and AWS server
last_sync_time = 0              # Last time we synced with AWS server
aws_time_socket = None          # TCP connection to AWS server for time sync
lock = threading.Lock()         # Lock for thread-safe updates to data
running = True                  # Flag to control thread execution
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
            
            with lock:
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



def get_synchronized_time():
    """Returns the current time synchronized with the AWS server."""
    with lock:
        current_offset = time_offset
    return time.time() - current_offset

def main():
    global aws_time_socket, running
    
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
        
        print(f"Time sync client running with interval {TIME_SYNC_INTERVAL}s")
        print("Press Ctrl+C to exit")
        
        # Keep the main thread running
        try:
            while running:
                # Display synchronized time every second
                current_time = get_synchronized_time()
                print(f"Synchronized time: {current_time:.6f}, Offset: {time_offset:.6f}s")
                time.sleep(1)
        except KeyboardInterrupt:
            print("Exiting...")
            running = False
    finally:
        # Close connections
        if aws_time_socket:
            aws_time_socket.close()

if __name__ == "__main__":
    main()
