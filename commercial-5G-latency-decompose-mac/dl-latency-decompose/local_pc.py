#!/usr/bin/env python3
import socket
import time
import struct
import threading
import argparse

# Configuration
CLOUD_SERVER_IP_PORT = 5000       # Port for timestamp service
TIME_SYNC_INTERVAL = 1          # Sync time with cloud server every second

# Global variables
time_offset = 0.0               # Time difference between client and cloud server
last_sync_time = 0              # Last time we synced with cloud server
cloud_time_socket = None          # TCP connection to cloud server for time sync
lock = threading.Lock()         # Lock for thread-safe updates to data
running = True                  # Flag to control thread execution
current_sync_rtt = 0.0          # Current RTT with cloud time server

def connect_to_cloud_time_server(cloud_server_ip):
    """Establish TCP connection to cloud server for time synchronization"""
    global cloud_time_socket
    
    while True:
        try:
            # Create TCP socket
            cloud_time_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Disable Nagle algorithm
            cloud_time_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            cloud_time_socket.connect((cloud_server_ip, CLOUD_SERVER_IP_PORT))
            print(f"Connected to cloud time server at {cloud_server_ip}:{CLOUD_SERVER_IP_PORT}")
            return
        except Exception as e:
            print(f"Failed to connect to cloud time server: {e}")
            print("Retrying in 5 seconds...")
            time.sleep(5)

def sync_with_cloud_server(cloud_server_ip):
    """Periodically sync time with cloud server"""
    global time_offset, last_sync_time, cloud_time_socket, running, current_sync_rtt
    
    while running:
        try:
            # Ensure we have a connection
            if cloud_time_socket is None:
                connect_to_cloud_time_server(cloud_server_ip)
                
            send_time = time.time()
            
            # Send empty packet as request to cloud server
            cloud_time_socket.sendall(b'x')  # Send a single byte as request
            
            # Receive response from cloud server
            data = cloud_time_socket.recv(1024)
            if not data:
                # Connection closed, try to reconnect
                print("Cloud server connection closed, reconnecting...")
                cloud_time_socket.close()
                cloud_time_socket = None
                connect_to_cloud_time_server(cloud_server_ip)
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
                
            print(f"Synced with cloud server - Offset: {offset:.6f}s, RTT: {rtt*1000:.2f}ms")
            
            # Wait for next sync interval
            time.sleep(TIME_SYNC_INTERVAL)
            
        except Exception as e:
            print(f"Error syncing with cloud server: {e}")
            # Close socket and try to reconnect next time
            if cloud_time_socket:
                cloud_time_socket.close()
                cloud_time_socket = None
            time.sleep(1)  # Wait before retrying



def get_synchronized_time():
    """Returns the current time synchronized with the cloud server."""
    with lock:
        current_offset = time_offset
    return time.time() - current_offset

def main():
    global cloud_time_socket, running
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Time synchronization client for cloud server')
    parser.add_argument('--cloud-ip', dest='cloud_server_ip', required=True,
                        help='IP address of the cloud server')
    parser.add_argument('--interval', type=float, default=1.0,
                        help='Time sync interval in seconds (default: 1.0)')
    args = parser.parse_args()
    
    # Update sync interval if specified
    global TIME_SYNC_INTERVAL
    TIME_SYNC_INTERVAL = args.interval
    
    try:
        # Connect to cloud server for time synchronization
        connect_to_cloud_time_server(args.cloud_server_ip)
        
        # Start thread for cloud server time sync
        cloud_sync_thread = threading.Thread(
            target=sync_with_cloud_server, 
            args=(args.cloud_server_ip,), 
            daemon=True
        )
        cloud_sync_thread.start()
        
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
        if cloud_time_socket:
            cloud_time_socket.close()

if __name__ == "__main__":
    main()
