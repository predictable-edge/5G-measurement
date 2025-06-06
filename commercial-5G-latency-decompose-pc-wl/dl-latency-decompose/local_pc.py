#!/usr/bin/env python3
import socket
import time
import struct
import threading
import argparse
import datetime
import os

# Configuration
CLOUD_SERVER_IP_PORT = 5000       # Port for timestamp service
CLOUD_SERVER_DATA_PORT = 5002     # Port for data communication with cloud server
PING_PONG_PORT = 5001             # Port for TCP ping-pong measurements
TIME_SYNC_INTERVAL = 1            # Sync time with cloud server every second
MAX_UDP_SEGMENT = 1300            # Maximum UDP segment size
UDP_BUFFER_SIZE = 4194304         # Buffer size for UDP socket (4MB)
TIMEOUT_SEC = 1                   # Timeout for UDP operations
PING_INTERVAL = 0.02              # Interval for ping-pong in seconds (20ms)

# Global variables
time_offset = 0.0                 # Time difference between client and Lz server
last_sync_time = 0                # Last time we synced with Lz server
lz_time_socket = None          # TCP connection to Lz server for time sync
cloud_data_socket = None          # UDP socket for cloud server data
ping_pong_socket = None           # UDP socket for ping-pong measurements
lock = threading.Lock()           # Lock for thread-safe updates to data
running = True                    # Flag to control thread execution
current_sync_rtt = 0.0            # Current RTT with cloud time server
measurement_count = 0             # Counter for received packets
results_file = None               # File to save measurement results
results_filename = None           # Filename for results
is_file_created = False           # Flag to indicate if results file is created

# Ping-pong measurements
ping_sequence = {}                # Dictionary to track {sequence: send_time}
ping_pong_rtts = []               # List to store RTT values
ping_pong_min_rtt = float('inf')  # Minimum RTT observed
ping_pong_max_rtt = 0.0           # Maximum RTT observed
ping_pong_avg_rtt = 0.0           # Average RTT
ping_pong_count = 0               # Number of ping-pongs completed
ping_pong_lock = threading.Lock() # Lock for ping-pong stats

def connect_to_lz_time_server(lz_server_ip, wifi_ip=None):
    """Establish TCP connection to Lz server for time synchronization"""
    global lz_time_socket
    
    while True:
        try:
            # Create TCP socket
            lz_time_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Disable Nagle algorithm
            lz_time_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            # Bind to specific local IP if provided (e.g., Wi-Fi interface)
            if wifi_ip:
                try:
                    lz_time_socket.bind((wifi_ip, 0))  # 0 means any available port
                    print(f"Time sync socket bound to Wi-Fi IP: {wifi_ip}")
                except Exception as bind_err:
                    print(f"Failed to bind time sync socket to {wifi_ip}: {bind_err}")
                    print("Continuing without binding to specific interface")
            
            lz_time_socket.connect((lz_server_ip, CLOUD_SERVER_IP_PORT)) # Assuming Lz server uses the same port for time sync
            print(f"Connected to Lz time server at {lz_server_ip}:{CLOUD_SERVER_IP_PORT}")
            return
        except Exception as e:
            print(f"Failed to connect to Lz time server: {e}")
            print("Retrying in 5 seconds...")
            time.sleep(5)

def sync_with_lz_server(lz_server_ip, wifi_ip=None):
    """Periodically sync time with Lz server"""
    global time_offset, last_sync_time, lz_time_socket, running, current_sync_rtt
    
    while running:
        try:
            # Ensure we have a connection
            if lz_time_socket is None:
                connect_to_lz_time_server(lz_server_ip, wifi_ip)
                
            send_time = time.time()
            
            # Send empty packet as request to Lz server
            lz_time_socket.sendall(b'x')  # Send a single byte as request
            
            # Receive response from Lz server
            data = lz_time_socket.recv(1024)
            if not data:
                # Connection closed, try to reconnect
                print("Lz server connection closed, reconnecting...")
                lz_time_socket.close()
                lz_time_socket = None
                connect_to_lz_time_server(lz_server_ip, wifi_ip)
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
                
            print(f"Synced with Lz server - Offset: {offset:.6f}s, RTT: {rtt*1000:.2f}ms")
            
            # Wait for next sync interval
            time.sleep(TIME_SYNC_INTERVAL)
            
        except Exception as e:
            print(f"Error syncing with Lz server: {e}")
            # Close socket and try to reconnect next time
            if lz_time_socket:
                lz_time_socket.close()
                lz_time_socket = None
            time.sleep(1)  # Wait before retrying

def get_synchronized_time():
    """Returns the current time synchronized with the Lz server."""
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

def flush_udp_buffer(sock):
    """Empty the UDP socket receive buffer by reading all pending packets"""
    # Save original timeout
    original_timeout = sock.gettimeout()
    # Set socket to non-blocking mode
    sock.setblocking(False)
    
    # Empty the buffer by reading until no more data
    flushed_packets = 0
    time.sleep(0.1)
    try:
        while True:
            try:
                sock.recvfrom(UDP_BUFFER_SIZE)
                flushed_packets += 1
            except BlockingIOError:
                # No more data to read
                break
            except Exception:
                # Any other exception
                break
    finally:
        # Restore original timeout
        sock.setblocking(True)
        sock.settimeout(original_timeout)
        if flushed_packets > 0:
            print(f"Flushed {flushed_packets} pending packets from receive buffer")
    return flushed_packets

def setup_cloud_data_socket(cloud_server_ip, mobile_ip=None):
    """Set up UDP socket for communication with cloud server"""
    global cloud_data_socket
    
    try:
        # Create UDP socket
        cloud_data_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Bind to specific local IP if provided (e.g., mobile interface)
        if mobile_ip:
            try:
                cloud_data_socket.bind((mobile_ip, 0))  # 0 means any available port
                print(f"Data socket bound to Mobile IP: {mobile_ip}")
            except Exception as bind_err:
                print(f"Failed to bind data socket to {mobile_ip}: {bind_err}")
                print("Continuing without binding to specific interface")
        
        # Set buffer sizes
        cloud_data_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, UDP_BUFFER_SIZE)
        cloud_data_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, UDP_BUFFER_SIZE)
        
        # Set timeout
        cloud_data_socket.settimeout(TIMEOUT_SEC)
        
        # Store server address
        cloud_server_address = (cloud_server_ip, CLOUD_SERVER_DATA_PORT)
        
        print(f"Set up UDP socket for cloud data server at {cloud_server_ip}:{CLOUD_SERVER_DATA_PORT}")
        return cloud_server_address
    except Exception as e:
        print(f"Failed to set up UDP socket for cloud data server: {e}")
        return None

def create_results_file(packet_size):
    """Create results file with packet size in the filename"""
    global results_file, results_filename
    
    # Create timestamp for filename
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create results file with packet size in the filename
    results_filename = f"udp_latency_bytes{packet_size}_{timestamp}.txt"
    results_file = open(results_filename, "w")
    
    # Write header to results file with fixed-width format
    results_file.write(f"{'index':<6s}  {'dl_delay_ms':<12s}  {'time_diff_ms':<14s}  {'duration_ms':<12s}  {'total_ms':<12s}  {'packet_size':<10s}  {'sync_rtt_ms':<10s}\n")
    results_file.write("-" * 80 + "\n")
    
    print(f"Saving results to {results_filename}")

def receive_data_from_server_udp(cloud_server_address, num_requests, interval_ms, bytes_per_request):
    """Receive data from cloud server using UDP and process it"""
    global cloud_data_socket, running, measurement_count, results_file, is_file_created, current_sync_rtt
    
    try:
        # Send parameters to server
        # num_requests, interval_ms, bytes_per_request
        params = struct.pack('!iii', num_requests, interval_ms, bytes_per_request)
        cloud_data_socket.sendto(params, cloud_server_address)
        
        print(f"Sent parameters to server: requests={num_requests}, interval={interval_ms}ms, bytes={bytes_per_request}")
        
        # Wait for acknowledgment with timeout
        try:
            ack, server_addr = cloud_data_socket.recvfrom(MAX_UDP_SEGMENT)
            if ack != b'ACK':
                print(f"Did not receive proper acknowledgment from server: {ack}")
                return False
        except socket.timeout:
            print("Timeout waiting for server acknowledgment")
            return False
            
        print("Server acknowledged parameters, ready to send trigger packets...")
        
        # Statistics tracking
        request_count = 0
        
        while request_count < num_requests and running:
            # Send trigger packet to request data
            cloud_data_socket.sendto(b'TRIG', cloud_server_address)
            print(f"Sent trigger packet for request {request_count+1}/{num_requests}")
            
            try:
                # First receive the header which contains request ID, timestamp, packet size, and total segments
                # Format: !IdII = 4-byte int (request ID) + 8-byte double + 4-byte unsigned int + 4-byte unsigned int = 20 bytes total
                header, server_addr = cloud_data_socket.recvfrom(MAX_UDP_SEGMENT)
                if not header or len(header) < 20:
                    if not header:
                        print("Empty response from server")
                    else:
                        print(f"Incomplete header received: {len(header)} bytes, expected 20 bytes")
                    continue
                
                # Parse the header to get request ID, timestamp, packet size, and total segments
                request_id, server_timestamp, packet_size, total_segments = struct.unpack('!IdII', header[:20])
                
                if server_timestamp == 0:
                    print("Server timestamp is 0, skipping request")
                    flush_udp_buffer(cloud_data_socket)  # Flush all pending packets
                    request_count += 1
                    continue
                
                # Record the time when header is received
                receive_time = time.time()
                
                # Create results file if this is the first packet with valid size
                if not is_file_created and packet_size >= 0:
                    create_results_file(packet_size)
                    is_file_created = True
                
                # Correct server timestamp using our time offset
                with lock:
                    corrected_server_time = server_timestamp - time_offset
                    sync_rtt = current_sync_rtt
                
                # Calculate DL transmission delay (server to client)
                dl_transmission_delay = receive_time - corrected_server_time
                
                # Calculate time difference in ms
                time_diff_ms = (receive_time - server_timestamp) * 1000
                
                # Output timestamps without correction
                print(f"Request {request_id}: Local timestamp: {receive_time:.6f}, Server timestamp: {server_timestamp:.6f}")
                print(f"Corrected server time: {corrected_server_time:.6f}")
                print(f"DL transmission delay: {dl_transmission_delay*1000:.2f} ms")
                print(f"Time difference: {time_diff_ms:.2f} ms")
                print(f"Current sync RTT: {sync_rtt*1000:.2f} ms")
                
                # Now receive the payload data in segments
                received_packet = bytearray()
                segments_received = 0
                
                # Start time for measuring packet reception duration
                packet_start_time = time.time()
                
                while segments_received < total_segments and running and len(received_packet) < packet_size:
                    try:
                        segment, addr = cloud_data_socket.recvfrom(MAX_UDP_SEGMENT)
                        
                        # Verify segment is from expected server
                        if addr != server_addr:
                            print(f"Received segment from unexpected address: {addr}, expected: {server_addr}")
                            continue
                            
                        # Extract request ID from segment (first 4 bytes)
                        if len(segment) < 4:
                            print(f"Segment too small, missing request ID: {len(segment)} bytes")
                            continue
                            
                        segment_request_id = struct.unpack('!I', segment[:4])[0]
                        
                        # Verify segment belongs to current request
                        if segment_request_id != request_id:
                            print(f"Segment has wrong request ID: {segment_request_id}, expected: {request_id}")
                            continue
                            
                        # Add segment data (excluding request ID) to received packet
                        received_packet.extend(segment[4:])
                        segments_received += 1
                        
                        if segments_received % 10 == 0 or segments_received == total_segments:
                            print(f"Received segment {segments_received}/{total_segments} for request ID {request_id}")
                            
                    except socket.timeout:
                        print(f"Timeout waiting for segment {segments_received+1}/{total_segments}")
                        # Flush the buffer if we time out during segment reception
                        flush_udp_buffer(cloud_data_socket)
                        break
                
                # If we received all segments
                if segments_received == total_segments:
                    # if len(received_packet) == packet_size:
                        # Increment measurement counter
                    measurement_count += 1
                    
                    # Calculate packet reception duration
                    packet_end_time = time.time()
                    duration_ms = (packet_end_time - packet_start_time) * 1000
                    
                    # Calculate total latency
                    total_latency_ms = dl_transmission_delay*1000 + duration_ms
                    
                    print(f"Packet fully received for request ID {request_id}. Duration: {duration_ms:.2f} ms, Packet size: {packet_size} bytes")
                    print(f"Total observed latency: {total_latency_ms:.2f} ms")
                    
                    # Save results to file with fixed-width format for better alignment
                    if results_file:
                        with lock:  # Use lock to avoid file corruption
                            results_file.write(f"{measurement_count:<6d}  {dl_transmission_delay*1000:<12.2f}  {time_diff_ms:<14.2f}  {duration_ms:<12.2f}  {total_latency_ms:<12.2f}  {packet_size:<10d}  {sync_rtt*1000:<10.2f}\n")
                            results_file.flush()  # Ensure data is written to disk
                    
                    request_count += 1
                    print(f"Saved measurement #{measurement_count} to file")
                    print("-" * 50)
                    # else:
                    #     print(f"Packet size mismatch for request ID {request_id}: received {len(received_packet)} bytes, expected {packet_size} bytes")
                    #     flush_udp_buffer(cloud_data_socket)  # Flush on error
                else:
                    print(f"Incomplete packet for request ID {request_id}: received {segments_received}/{total_segments} segments")
                    flush_udp_buffer(cloud_data_socket)  # Flush on incomplete segments
                    
            except socket.timeout:
                print(f"Timeout waiting for response for request {request_count+1}")
                flush_udp_buffer(cloud_data_socket)  # Flush on timeout
                continue
            
            # Sleep for the specified interval before sending the next trigger
            if request_count < num_requests:
                interval_sec = interval_ms / 1000.0
                time.sleep(interval_sec)
        
        # Print summary
        if request_count > 0:
            print(f"\nReceived {request_count}/{num_requests} requests")
        
        return request_count == num_requests
    
    except Exception as e:
        print(f"Error receiving data from server: {e}")
        return False

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
                                    # print("\n")
                                    # print(f"Ping-pong stats - Count: {ping_pong_count}, Min: {ping_pong_min_rtt:.2f}ms, " + 
                                    #       f"Avg: {ping_pong_avg_rtt:.2f}ms, Max: {ping_pong_max_rtt:.2f}ms")
                                    # print("\n")
                                    
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
    global cloud_time_socket, cloud_data_socket, running, results_file, ping_pong_socket, lz_time_socket
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Time synchronization and data collection client')
    parser.add_argument('--cloud-ip', dest='cloud_server_ip',
                        help='IP address of the cloud server (required for data communication)')
    parser.add_argument('--lz-ip', dest='lz_server_ip',
                        help='IP address of the Lz server (required for time synchronization)')
    parser.add_argument('--wifi-ip', dest='wifi_ip', 
                        help='Wi-Fi IP address to bind for time synchronization (required, format: x.x.x.x)')
    parser.add_argument('--mobile-ip', dest='mobile_ip', 
                        help='Mobile IP address to bind for UDP data communication (required, format: x.x.x.x)')
    parser.add_argument('--interval', type=float, default=1.0,
                        help='Time sync interval in seconds (default: 1.0)')
    parser.add_argument('--list-interfaces', action='store_true',
                        help='List available network interfaces and exit')
    parser.add_argument('--requests', type=int, default=100,
                        help='Number of requests to receive (default: 100)')
    parser.add_argument('--request-interval', type=int, default=1000,
                        help='Interval between requests in milliseconds (default: 1000)')
    parser.add_argument('--bytes', type=int, default=0,
                        help='Number of bytes per request (default: 0)')
    parser.add_argument('--no-ping-pong', action='store_true',
                        help='Disable UDP ping-pong testing (not recommended)')
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
        parser.error("--cloud-ip is required. Please specify the IP address of the cloud server for data communication.")
    
    if not args.lz_server_ip:
        parser.error("--lz-ip is required. Please specify the IP address of the Lz server for time synchronization.")
    
    if not args.wifi_ip:
        parser.error("--wifi-ip is required. Please specify the IP address of your Wi-Fi interface for time synchronization with Lz server.\n"
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
    
    # Update sync interval if specified
    global TIME_SYNC_INTERVAL
    TIME_SYNC_INTERVAL = args.interval
    
    try:
        # Connect to Lz server for time synchronization
        connect_to_lz_time_server(args.lz_server_ip, args.wifi_ip)
        
        # Start thread for Lz server time sync
        lz_sync_thread = threading.Thread(
            target=sync_with_lz_server, 
            args=(args.lz_server_ip, args.wifi_ip), 
            daemon=True
        )
        lz_sync_thread.start()
        
        print(f"Time sync client running with Lz server at {args.lz_server_ip} with interval {TIME_SYNC_INTERVAL}s")
        if args.wifi_ip:
            print(f"Using Wi-Fi interface with IP: {args.wifi_ip} for time synchronization")
        
        # Start ping-pong UDP latency testing with cloud server
        if not args.no_ping_pong:
            print(f"Starting UDP ping-pong testing to {args.cloud_server_ip} using interface {args.mobile_ip}")
            ping_pong_socket, _, _ = ping_pong_client(args.cloud_server_ip, args.mobile_ip)
        
        # Wait for time synchronization to stabilize
        print("Waiting for time synchronization to stabilize (3 seconds)...")
        time.sleep(3)
        
        # Set up UDP socket for cloud server data
        cloud_server_address = setup_cloud_data_socket(args.cloud_server_ip, args.mobile_ip)
        if not cloud_server_address:
            print("Failed to set up UDP socket for cloud server, exiting...")
            running = False
            return
        
        if args.mobile_ip:
            print(f"Using Mobile interface with IP: {args.mobile_ip} for data communication")
        
        # Receive data from server
        receive_data_from_server_udp(
            cloud_server_address, 
            args.requests, 
            args.request_interval, 
            args.bytes
        )
            
    except KeyboardInterrupt:
        print("Exiting...")
        running = False
    finally:
        # Close connections
        if lz_time_socket:
            lz_time_socket.close()
        if cloud_data_socket:
            cloud_data_socket.close()
        if ping_pong_socket:
            ping_pong_socket.close()
        
        # Close results file
        if results_file:
            results_file.close()
            if results_filename:
                print(f"Results saved to {results_filename}")

if __name__ == "__main__":
    main()
