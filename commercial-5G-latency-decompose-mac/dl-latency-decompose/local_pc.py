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

def connect_to_cloud_time_server(cloud_server_ip, local_ip=None):
    """Establish TCP connection to cloud server for time synchronization"""
    global cloud_time_socket
    
    while True:
        try:
            # Create TCP socket
            cloud_time_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Disable Nagle algorithm
            cloud_time_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            # Bind to specific local IP if provided (e.g., Wi-Fi interface)
            if local_ip:
                try:
                    cloud_time_socket.bind((local_ip, 0))  # 0 means any available port
                    print(f"Bound to local IP: {local_ip}")
                except Exception as bind_err:
                    print(f"Failed to bind to {local_ip}: {bind_err}")
                    print("Continuing without binding to specific interface")
            
            cloud_time_socket.connect((cloud_server_ip, CLOUD_SERVER_IP_PORT))
            print(f"Connected to cloud time server at {cloud_server_ip}:{CLOUD_SERVER_IP_PORT}")
            return
        except Exception as e:
            print(f"Failed to connect to cloud time server: {e}")
            print("Retrying in 5 seconds...")
            time.sleep(5)

def sync_with_cloud_server(cloud_server_ip, local_ip=None):
    """Periodically sync time with cloud server"""
    global time_offset, last_sync_time, cloud_time_socket, running, current_sync_rtt
    
    while running:
        try:
            # Ensure we have a connection
            if cloud_time_socket is None:
                connect_to_cloud_time_server(cloud_server_ip, local_ip)
                
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
                connect_to_cloud_time_server(cloud_server_ip, local_ip)
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

def get_local_interfaces():
    """Returns a list of local network interfaces with their IP addresses"""
    interfaces = []
    
    try:
        import netifaces
        for iface in netifaces.interfaces():
            try:
                addrs = netifaces.ifaddresses(iface)
                # Get IPv4 addresses
                if netifaces.AF_INET in addrs:
                    for addr in addrs[netifaces.AF_INET]:
                        if 'addr' in addr:
                            interfaces.append((iface, addr['addr']))
            except Exception:
                pass
    except ImportError:
        # Fallback if netifaces isn't available
        try:
            import subprocess
            import re
            
            # For macOS
            output = subprocess.check_output(['ifconfig']).decode('utf-8')
            pattern = r'(en\d+|wlan\d+).*?inet\s+(\d+\.\d+\.\d+\.\d+)'
            for match in re.finditer(pattern, output, re.DOTALL):
                interfaces.append((match.group(1), match.group(2)))
        except Exception as e:
            print(f"Could not determine network interfaces: {e}")
    
    return interfaces

def main():
    global cloud_time_socket, running
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Time synchronization client for cloud server')
    parser.add_argument('--cloud-ip', dest='cloud_server_ip',
                        help='IP address of the cloud server')
    parser.add_argument('--local-ip', dest='local_ip', 
                        help='Local IP address to bind to (e.g., Wi-Fi interface IP)')
    parser.add_argument('--interval', type=float, default=1.0,
                        help='Time sync interval in seconds (default: 1.0)')
    parser.add_argument('--list-interfaces', action='store_true',
                        help='List available network interfaces and exit')
    args = parser.parse_args()
    
    # List interfaces if requested
    if args.list_interfaces:
        interfaces = get_local_interfaces()
        if interfaces:
            print("Available network interfaces:")
            for iface, ip in interfaces:
                print(f"  {iface}: {ip}")
        else:
            print("No network interfaces found or unable to determine interfaces")
        return
    
    # Check required arguments
    if not args.cloud_server_ip:
        parser.error("--cloud-ip is required unless --list-interfaces is specified")
    
    # Update sync interval if specified
    global TIME_SYNC_INTERVAL
    TIME_SYNC_INTERVAL = args.interval
    
    try:
        # Connect to cloud server for time synchronization
        connect_to_cloud_time_server(args.cloud_server_ip, args.local_ip)
        
        # Start thread for cloud server time sync
        cloud_sync_thread = threading.Thread(
            target=sync_with_cloud_server, 
            args=(args.cloud_server_ip, args.local_ip), 
            daemon=True
        )
        cloud_sync_thread.start()
        
        print(f"Time sync client running with interval {TIME_SYNC_INTERVAL}s")
        if args.local_ip:
            print(f"Using local network interface with IP: {args.local_ip}")
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
