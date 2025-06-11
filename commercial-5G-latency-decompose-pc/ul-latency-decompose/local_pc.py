#!/usr/bin/env python3
import socket
import time
import struct
import threading
import argparse

# Configuration
CLOUD_SERVER_IP_PORT = 5000     # Port for timestamp service
CLOUD_SERVER_UDP_PORT = 5002    # Cloud server UDP port for data transmission
PING_PONG_PORT = 5001           # Port for UDP ping-pong measurements
TIME_SYNC_INTERVAL = 1          # Expected sync interval from cloud server
PACKET_INTERVAL = 1             # Time between sending packets (seconds)
MAX_UDP_SEGMENT = 1300          # Maximum UDP segment size
PING_INTERVAL = 0.02            # Interval for ping-pong in seconds (20ms)

# Global variables
cloud_time_socket = None        # TCP connection to cloud server for time sync
cloud_udp_socket = None         # UDP socket for cloud server communication
ping_pong_socket = None         # UDP socket for ping-pong measurements
running = True                  # Flag to control thread execution
num_requests = 10               # Number of requests to send
bytes_per_request = 1           # Number of bytes per request

# Ping-pong measurements
ping_sequence = {}                # Dictionary to track {sequence: send_time}
ping_pong_rtts = []               # List to store RTT values
ping_pong_min_rtt = float('inf')  # Minimum RTT observed
ping_pong_max_rtt = 0.0           # Maximum RTT observed
ping_pong_avg_rtt = 0.0           # Average RTT
ping_pong_count = 0               # Number of ping-pongs completed
ping_pong_lock = threading.Lock() # Lock for ping-pong stats

def connect_to_cloud_time_server(cloud_server_ip, wifi_ip=None):
    """Establish TCP connection to cloud server for time synchronization"""
    global cloud_time_socket
    
    while True:
        try:
            # Create TCP socket
            cloud_time_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Disable Nagle algorithm
            cloud_time_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            # Bind to specific local IP if provided (e.g., wifi interface)
            if wifi_ip:
                try:
                    cloud_time_socket.bind((wifi_ip, 0))  # 0 means any available port
                    print(f"Time sync socket bound to Wi-Fi IP: {wifi_ip}")
                except Exception as bind_err:
                    print(f"Failed to bind time sync socket to {wifi_ip}: {bind_err}")
                    print("Continuing without binding to specific interface")
            
            cloud_time_socket.connect((cloud_server_ip, CLOUD_SERVER_IP_PORT))
            print(f"Connected to cloud time server at {cloud_server_ip}:{CLOUD_SERVER_IP_PORT}")
            return
        except Exception as e:
            print(f"Failed to connect to cloud time server: {e}")
            print("Retrying in 5 seconds...")
            time.sleep(5)

def listen_for_cloud_sync():
    """Listen for time sync packets from cloud server and respond"""
    global cloud_time_socket, running
    
    try:
        while running:
            try:
                # Wait for timestamp from cloud server
                data = cloud_time_socket.recv(8)  # Expect an 8-byte double
                if not data or len(data) < 8:
                    # Connection closed or invalid data
                    if not data:
                        print("Cloud server connection closed, reconnecting...")
                    else:
                        print(f"Received invalid data from cloud server: {len(data)} bytes, expected 8")
                    
                    # Try to reconnect
                    cloud_time_socket.close()
                    cloud_time_socket = None
                    break
                
                # Unpack server timestamp
                server_timestamp = struct.unpack('!d', data)[0]
                
                # Send our current time back to server
                client_timestamp = time.time()
                response = struct.pack('!d', client_timestamp)
                cloud_time_socket.sendall(response)
                
                print(f"Received sync from cloud - Server time: {server_timestamp:.6f}, responded with: {client_timestamp:.6f}")
                
            except socket.timeout:
                # Socket timeout, just continue the loop
                continue
            except ConnectionError as e:
                print(f"Connection error with cloud server: {e}")
                cloud_time_socket.close()
                cloud_time_socket = None
                break
            except Exception as e:
                print(f"Error handling cloud sync: {e}")
                time.sleep(1)  # Avoid tight loop
    
    except Exception as e:
        print(f"Error in cloud sync listener: {e}")
        
    finally:
        # Handle reconnection in the main thread
        if not cloud_time_socket and running:
            print("Cloud sync listener exited, will reconnect")

def maintain_cloud_connection(cloud_server_ip, wifi_ip=None):
    """Maintain connection to cloud server and handle reconnections"""
    global cloud_time_socket, running
    
    while running:
        if cloud_time_socket is None:
            # Need to connect/reconnect
            connect_to_cloud_time_server(cloud_server_ip, wifi_ip)
            
            # Start a new thread to listen for time sync from cloud
            sync_thread = threading.Thread(
                target=listen_for_cloud_sync,
                daemon=True
            )
            sync_thread.start()
        
        # Check periodically if we need to reconnect
        time.sleep(5)

def setup_cloud_udp_socket(mobile_ip=None):
    """Set up UDP socket for communication with cloud server"""
    global cloud_udp_socket
    
    try:
        # Create UDP socket
        cloud_udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Bind to specific local IP if provided (e.g., mobile interface)
        if mobile_ip:
            try:
                cloud_udp_socket.bind((mobile_ip, 0))  # 0 means any available port
                print(f"UDP socket bound to Mobile IP: {mobile_ip}")
            except Exception as bind_err:
                print(f"Failed to bind UDP socket to {mobile_ip}: {bind_err}")
                print("Continuing without binding to specific interface")
        
        print(f"Set up UDP socket for cloud server communication")
        return True
    except Exception as e:
        print(f"Failed to set up UDP socket: {e}")
        return False

def send_data_to_cloud(cloud_server_ip, mobile_ip=None):
    """Send data to cloud server over UDP"""
    global cloud_udp_socket, running, num_requests, bytes_per_request
    
    # Set up UDP socket if not already done
    if cloud_udp_socket is None:
        if not setup_cloud_udp_socket(mobile_ip):
            print("Failed to set up UDP socket for cloud server")
            return
    
    try:
        # Create destination address
        cloud_address = (cloud_server_ip, CLOUD_SERVER_UDP_PORT)
        
        # Send data requests
        requests_sent = 0
        
        while running and requests_sent < num_requests:
            try:
                # Create request ID (1-based)
                request_id = requests_sent + 1
                
                # Get current timestamp
                timestamp = time.time()
                
                # Create header with request_id, timestamp, and size
                # Format: !IdI = 4-byte unsigned int + 8-byte double + 4-byte unsigned int = 16 bytes total
                header = struct.pack('!IdI', request_id, timestamp, bytes_per_request)
                
                # Send header to cloud server
                cloud_udp_socket.sendto(header, cloud_address)
                print(f"Sent header to cloud server - Request ID: {request_id}, Timestamp: {timestamp:.6f}")
                
                # Create payload of specified size if needed
                if bytes_per_request > 0:
                    payload = b'\x00' * bytes_per_request
                    
                    # Split payload into segments if needed
                    segments_sent = 0
                    total_segments = (bytes_per_request + MAX_UDP_SEGMENT - 5) // (MAX_UDP_SEGMENT - 4) if bytes_per_request > 0 else 0
                    
                    for i in range(0, bytes_per_request, MAX_UDP_SEGMENT - 4):
                        # Get segment size
                        segment_end = min(i + MAX_UDP_SEGMENT - 4, bytes_per_request)
                        
                        # Get the segment data
                        segment_data = payload[i:segment_end]
                        
                        # Add request ID to each segment (4 bytes)
                        segment = struct.pack('!I', request_id) + segment_data
                        
                        # Send segment
                        cloud_udp_socket.sendto(segment, cloud_address)
                        segments_sent += 1
                        
                        if segments_sent % 10 == 0 or segments_sent == total_segments:
                            print(f"Sent segment {segments_sent}/{total_segments} to cloud server")
                
                requests_sent += 1
                print(f"Completed sending request {request_id}/{num_requests} to cloud server - Size: {bytes_per_request} bytes")
                
                # Sleep before sending next packet
                time.sleep(PACKET_INTERVAL)
                
            except Exception as e:
                print(f"Error sending data to cloud server: {e}")
                time.sleep(1)  # Avoid tight loop on error
        
        print(f"Completed sending all {requests_sent}/{num_requests} requests to cloud server")
    
    except Exception as e:
        print(f"Error in data sending thread: {e}")

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
            
            # Check which OS we're on
            import platform
            os_type = platform.system().lower()
            
            if 'darwin' in os_type:  # macOS
                output = subprocess.check_output(['ifconfig']).decode('utf-8')
                pattern = r'(en\d+|wlan\d+).*?inet\s+(\d+\.\d+\.\d+\.\d+)'
                for match in re.finditer(pattern, output, re.DOTALL):
                    interfaces.append((match.group(1), match.group(2)))
            elif 'windows' in os_type:  # Windows
                # Use ipconfig to get interfaces on Windows
                output = subprocess.check_output(['ipconfig', '/all']).decode('utf-8', errors='ignore')
                sections = output.split('\r\n\r\n')
                
                current_iface = None
                for section in sections:
                    lines = section.split('\r\n')
                    if len(lines) > 0 and ':' in lines[0]:
                        # This is an interface section
                        current_iface = lines[0].strip()
                        
                        # Look for IPv4 Address in this section
                        for line in lines:
                            if 'IPv4 Address' in line and ':' in line:
                                parts = line.split(':')
                                if len(parts) >= 2:
                                    # Clean up the IP address
                                    ip = parts[1].strip()
                                    # Remove (Preferred) suffix if present
                                    ip = ip.split('(')[0].strip()
                                    # Exclude loopback
                                    if ip != '127.0.0.1' and current_iface:
                                        interfaces.append((current_iface, ip))
            elif 'linux' in os_type:  # Linux
                # Use a simpler approach for Linux
                try:
                    # Try using ip command first
                    output = subprocess.check_output(['ip', 'addr']).decode('utf-8')
                    lines = output.splitlines()
                    
                    current_iface = None
                    for line in lines:
                        # Get interface name
                        if ': ' in line and not line.startswith(' '):
                            parts = line.split(': ')
                            if len(parts) >= 2:
                                current_iface = parts[1].split('@')[0]
                        
                        # Get IPv4 address
                        if current_iface and 'inet ' in line and 'inet6' not in line:
                            parts = line.strip().split()
                            for i, part in enumerate(parts):
                                if part == 'inet' and i+1 < len(parts):
                                    ip = parts[i+1].split('/')[0]
                                    if ip != '127.0.0.1':  # Skip loopback
                                        interfaces.append((current_iface, ip))
                                        break
                
                except (subprocess.SubprocessError, FileNotFoundError):
                    # Fallback to ifconfig
                    output = subprocess.check_output(['ifconfig']).decode('utf-8')
                    lines = output.splitlines()
                    
                    current_iface = None
                    for line in lines:
                        # Get interface name
                        if ' ' in line and not line.startswith(' '):
                            current_iface = line.split(' ')[0]
                        
                        # Get IPv4 address
                        if current_iface and 'inet ' in line and 'inet6' not in line:
                            parts = line.strip().split()
                            for i, part in enumerate(parts):
                                if part == 'inet' and i+1 < len(parts):
                                    ip = parts[i+1].split('/')[0]
                                    if 'addr:' in ip:
                                        ip = ip.split('addr:')[1]
                                    if ip != '127.0.0.1':  # Skip loopback
                                        interfaces.append((current_iface, ip))
                                        break
        except Exception as e:
            print(f"Could not determine network interfaces: {e}")
    
    return interfaces

def send_ping_thread(socket_obj, server_address):
    """
    Thread function to continuously send ping packets to the server.
    
    Args:
        socket_obj: The shared UDP socket to use
        server_address: Tuple of (IP, port) for the server
    """
    global running, ping_sequence
    
    try:
        print(f"Starting to send ping packets to {server_address}")
        
        # Main ping sending loop
        sequence = 0
        while running:
            sequence += 1
            start_time = time.time()
            
            # Send ping message with sequence number
            message = f"PING:{sequence}".encode()
            socket_obj.sendto(message, server_address)
            
            # Store the send time with the sequence number
            with ping_pong_lock:
                ping_sequence[sequence] = start_time
                
                # Debug output for every 1000th message
                if sequence % 1000 == 0:
                    print(f"Sent ping {sequence} at {start_time:.6f}")
            
            # Sleep until next interval - adjust for processing time
            sleep_time = PING_INTERVAL - (time.time() - start_time)
            if sleep_time > 0:
                time.sleep(sleep_time)
    
    except Exception as e:
        print(f"Error in ping sender thread: {e}")

def receive_pong_thread(socket_obj):
    """
    Thread function to continuously receive pong responses from the server.
    
    Args:
        socket_obj: The shared UDP socket to use
    """
    global running, ping_sequence, ping_pong_rtts, ping_pong_min_rtt, ping_pong_max_rtt, ping_pong_avg_rtt, ping_pong_count
    
    try:
        print(f"Ping receiver starting to listen for responses")
        
        # Stats for packet analysis
        packets_received = 0
        
        # Main pong receiving loop
        while running:
            # Receive pong response
            try:
                socket_obj.settimeout(1.0)  # 1 second timeout
                data, addr = socket_obj.recvfrom(2048)  # Increase buffer size
                
                # Process the response
                try:
                    message = data.decode()
                    
                    if message.startswith("PONG:"):
                        # Extract sequence number
                        sequence = int(message.split(":")[1])
                        
                        # Calculate RTT if we have the send time
                        with ping_pong_lock:
                            if sequence in ping_sequence:
                                send_time = ping_sequence[sequence]
                                receive_time = time.time()
                                rtt = (receive_time - send_time) * 1000  # Convert to milliseconds
                                
                                # Update statistics
                                ping_pong_count += 1
                                ping_pong_rtts.append(rtt)
                                ping_pong_min_rtt = min(ping_pong_min_rtt, rtt) if ping_pong_min_rtt != float('inf') else rtt
                                ping_pong_max_rtt = max(ping_pong_max_rtt, rtt)
                                ping_pong_avg_rtt = sum(ping_pong_rtts) / len(ping_pong_rtts)
                                
                                # Delete old sequence to prevent memory leak
                                del ping_sequence[sequence]
                                
                                # Log stats periodically
                                packets_received += 1
                                if ping_pong_count % 100 == 0:
                                    print(f"Ping-pong stats - Count: {ping_pong_count}, Min: {ping_pong_min_rtt:.2f}ms, " + 
                                          f"Avg: {ping_pong_avg_rtt:.2f}ms, Max: {ping_pong_max_rtt:.2f}ms")
                                    
                                    # Clean up old sequence numbers (if any left)
                                    current_time = time.time()
                                    old_sequences = [seq for seq, t in ping_sequence.items() if current_time - t > 5]
                                    for seq in old_sequences:
                                        del ping_sequence[seq]
                            else:
                                # This can happen if the pong response is very delayed
                                print(f"Received pong for unknown sequence: {sequence}")
                    else:
                        print(f"Unexpected message format: {message}")
                except Exception as e:
                    print(f"Error processing pong message: {e}")
                    continue
                    
            except socket.timeout:
                print("No pong received in the last second")
                continue
            except Exception as e:
                print(f"Error receiving pong: {e}")
                if not running:
                    break
                continue
    
    except Exception as e:
        print(f"Error in pong receiver thread: {e}")

def ping_pong_client(cloud_server_ip, mobile_ip=None):
    """
    Create UDP ping-pong measurement between client and server.
    One thread sends pings, another receives pongs.
    
    Args:
        cloud_server_ip: IP address of the cloud server
        mobile_ip: Optional mobile interface IP to bind to
    """
    global ping_sequence
    
    # Initialize sequence tracking
    ping_sequence = {}  # Dictionary to track {sequence: send_time}
    
    try:
        # Create a single shared UDP socket
        ping_pong_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Bind to specific interface if provided
        if mobile_ip:
            try:
                ping_pong_socket.bind((mobile_ip, 0))  # 0 = any available port
                print(f"Ping-pong socket bound to Mobile IP: {mobile_ip}")
            except Exception as bind_err:
                print(f"Failed to bind ping-pong socket to {mobile_ip}: {bind_err}")
                print("Continuing without binding to specific interface")
        
        # Get the local port we're bound to
        local_addr = ping_pong_socket.getsockname()
        print(f"Ping-pong socket using local address: {local_addr}")
        
        # Server address
        server_address = (cloud_server_ip, PING_PONG_PORT)
        
        # Start receiver thread
        receiver = threading.Thread(
            target=receive_pong_thread,
            args=(ping_pong_socket,),
            daemon=True
        )
        receiver.start()
        
        # Wait a moment to ensure receiver is listening
        time.sleep(0.1)
        
        # Start sender thread
        sender = threading.Thread(
            target=send_ping_thread,
            args=(ping_pong_socket, server_address),
            daemon=True
        )
        sender.start()
        
        print(f"Ping-pong client started with sender and receiver threads")
        
        # Return the socket so it can be properly closed
        return ping_pong_socket, sender, receiver
        
    except Exception as e:
        print(f"Error setting up ping-pong client: {e}")
        return None, None, None

def main():
    global cloud_time_socket, cloud_udp_socket, running, num_requests, bytes_per_request, PACKET_INTERVAL, ping_pong_socket
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Time synchronization and data transmission client')
    parser.add_argument('--cloud-ip', dest='cloud_server_ip', required=True,
                        help='IP address of the cloud server')
    parser.add_argument('--mobile-ip', dest='mobile_ip', 
                        help='Mobile IP address to bind for UDP data communication (required, format: x.x.x.x)')
    parser.add_argument('--wifi-ip', dest='wifi_ip', 
                        help='Wi-Fi IP address to bind for time synchronization (required, format: x.x.x.x)')
    parser.add_argument('--requests', type=int, default=10,
                        help='Number of requests to send to cloud server (default: 10)')
    parser.add_argument('--bytes', type=int, default=1,
                        help='Size in bytes per request (default: 1)')
    parser.add_argument('--interval', type=int, default=1000,
                        help='Interval between packets in milliseconds (default: 1000)')
    parser.add_argument('--list-interfaces', action='store_true',
                        help='List available network interfaces and exit')
    parser.add_argument('--no-ping-pong', action='store_true',
                        help='Disable UDP ping-pong testing')
    args = parser.parse_args()
    
    # List interfaces if requested
    if args.list_interfaces:
        interfaces = get_local_interfaces()
        if interfaces:
            print("Available network interfaces:")
            for iface, ip in interfaces:
                print(f"  {iface}: {ip}")
            print("\nExample usage:")
            print("  python3 local_pc.py --cloud-ip 192.168.1.100 --wifi-ip 192.168.1.5 --mobile-ip 10.0.0.5")
        else:
            print("No network interfaces found or unable to determine interfaces")
        return
    
    # Check required arguments
    if not args.cloud_server_ip:
        parser.error("--cloud-ip is required. Please specify the IP address of the cloud server.")
    
    if not args.wifi_ip:
        parser.error("--wifi-ip is required. Please specify the IP address of your Wi-Fi interface.\n"
                    "Use --list-interfaces to see available network interfaces.")
    
    if not args.mobile_ip:
        parser.error("--mobile-ip is required. Please specify the IP address of your mobile interface.\n"
                    "Use --list-interfaces to see available network interfaces.")
    
    # Check if provided IP addresses exist in local interfaces
    interfaces = get_local_interfaces()
    # available_ips = [ip for _, ip in interfaces]
    
    # if args.wifi_ip not in available_ips:
    #     parser.error(f"Wi-Fi IP {args.wifi_ip} not found in local network interfaces.\n"
    #                 "Use --list-interfaces to see available network interfaces.")
    
    # if args.mobile_ip not in available_ips:
    #     parser.error(f"Mobile IP {args.mobile_ip} not found in local network interfaces.\n"
    #                 "Use --list-interfaces to see available network interfaces.")
    
    # Update request parameters
    num_requests = args.requests
    bytes_per_request = args.bytes
    # Convert interval from milliseconds to seconds
    PACKET_INTERVAL = args.interval / 1000.0
    
    try:
        # Start thread to maintain cloud server connection for time sync
        cloud_thread = threading.Thread(
            target=maintain_cloud_connection,
            args=(args.cloud_server_ip, args.wifi_ip),
            daemon=True
        )
        cloud_thread.start()
        
        print(f"Local client running, responding to time sync requests from cloud server")
        print(f"Using Wi-Fi IP: {args.wifi_ip} for time synchronization")
        
        # Start ping-pong UDP latency testing
        if not args.no_ping_pong:
            print(f"Starting UDP ping-pong testing to {args.cloud_server_ip} using interface {args.mobile_ip}")
            ping_pong_socket, _, _ = ping_pong_client(args.cloud_server_ip, args.mobile_ip)
        
        # Wait for time synchronization to stabilize
        print("Waiting for time synchronization to stabilize (3 seconds)...")
        time.sleep(3)
        
        # Start thread to send data to cloud server
        data_thread = threading.Thread(
            target=send_data_to_cloud,
            args=(args.cloud_server_ip, args.mobile_ip),
            daemon=True
        )
        data_thread.start()
        
        print(f"Ready to send {num_requests} requests with {bytes_per_request} bytes each to cloud server")
        print(f"Using Mobile IP: {args.mobile_ip} for data transmission")
        print(f"Sending data to cloud server at {args.cloud_server_ip}:{CLOUD_SERVER_UDP_PORT}")
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
        if cloud_time_socket:
            cloud_time_socket.close()
        if cloud_udp_socket:
            cloud_udp_socket.close()
        if ping_pong_socket:
            ping_pong_socket.close()

if __name__ == "__main__":
    main()
