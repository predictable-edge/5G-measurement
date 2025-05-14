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
TIME_SYNC_INTERVAL = 1            # Sync time with cloud server every second
MAX_UDP_SEGMENT = 4096            # Maximum UDP segment size
UDP_BUFFER_SIZE = 4194304         # Buffer size for UDP socket (4MB)
TIMEOUT_SEC = 1                   # Timeout for UDP operations

# Global variables
time_offset = 0.0                 # Time difference between client and cloud server
last_sync_time = 0                # Last time we synced with cloud server
cloud_time_socket = None          # TCP connection to cloud server for time sync
cloud_data_socket = None          # UDP socket for cloud server data
lock = threading.Lock()           # Lock for thread-safe updates to data
running = True                    # Flag to control thread execution
current_sync_rtt = 0.0            # Current RTT with cloud time server
measurement_count = 0             # Counter for received packets
results_file = None               # File to save measurement results
results_filename = None           # Filename for results
is_file_created = False           # Flag to indicate if results file is created

def connect_to_cloud_time_server(cloud_server_ip, wifi_ip=None):
    """Establish TCP connection to cloud server for time synchronization"""
    global cloud_time_socket
    
    while True:
        try:
            # Create TCP socket
            cloud_time_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Disable Nagle algorithm
            cloud_time_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            # Bind to specific local IP if provided (e.g., Wi-Fi interface)
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

def sync_with_cloud_server(cloud_server_ip, wifi_ip=None):
    """Periodically sync time with cloud server"""
    global time_offset, last_sync_time, cloud_time_socket, running, current_sync_rtt
    
    while running:
        try:
            # Ensure we have a connection
            if cloud_time_socket is None:
                connect_to_cloud_time_server(cloud_server_ip, wifi_ip)
                
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
                connect_to_cloud_time_server(cloud_server_ip, wifi_ip)
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
                    if len(received_packet) == packet_size:
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
                    else:
                        print(f"Packet size mismatch for request ID {request_id}: received {len(received_packet)} bytes, expected {packet_size} bytes")
                        flush_udp_buffer(cloud_data_socket)  # Flush on error
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

def main():
    global cloud_time_socket, cloud_data_socket, running, results_file
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Time synchronization and data collection client')
    parser.add_argument('--cloud-ip', dest='cloud_server_ip',
                        help='IP address of the cloud server (required)')
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
    
    # Update sync interval if specified
    global TIME_SYNC_INTERVAL
    TIME_SYNC_INTERVAL = args.interval
    
    try:
        # Connect to cloud server for time synchronization
        connect_to_cloud_time_server(args.cloud_server_ip, args.wifi_ip)
        
        # Start thread for cloud server time sync
        cloud_sync_thread = threading.Thread(
            target=sync_with_cloud_server, 
            args=(args.cloud_server_ip, args.wifi_ip), 
            daemon=True
        )
        cloud_sync_thread.start()
        
        print(f"Time sync client running with interval {TIME_SYNC_INTERVAL}s")
        if args.wifi_ip:
            print(f"Using Wi-Fi interface with IP: {args.wifi_ip} for time synchronization")
        
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
        if cloud_time_socket:
            cloud_time_socket.close()
        if cloud_data_socket:
            cloud_data_socket.close()
        
        # Close results file
        if results_file:
            results_file.close()
            if results_filename:
                print(f"Results saved to {results_filename}")

if __name__ == "__main__":
    main()
