import argparse
import socket
import struct
import time
import random
import datetime
import os
import threading
from collections import defaultdict

# Maximum UDP packet size (practically safe)
MAX_UDP_PACKET = 8192
# UDP port for data communication
UDP_PORT = 5000
# UDP port for ping-pong measurements
PING_PONG_PORT = 5001
# Interval for ping-pong in seconds (20ms)
PING_INTERVAL = 0.02

# Message types
MSG_TYPE_CONTROL = 1
MSG_TYPE_REQUEST = 2

# Global request counter
request_counter = 0

# Response tracking
response_buffer = defaultdict(dict)  # {request_id: {chunk_id: data}}

# Results tracking
results_file = None             # File to save measurement results
measurement_count = 0           # Counter for received packets

# Ping-pong measurements
ping_pong_socket = None         # UDP socket for ping-pong measurements
ping_sequence = {}              # Dictionary to track {sequence: send_time}
ping_pong_rtts = []             # List to store RTT values
ping_pong_min_rtt = float('inf')  # Minimum RTT observed
ping_pong_max_rtt = 0.0         # Maximum RTT observed
ping_pong_avg_rtt = 0.0         # Average RTT
ping_pong_count = 0             # Number of ping-pongs completed
ping_pong_lock = threading.Lock() # Lock for ping-pong stats
running = True                  # Flag to control thread execution

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

def parse_arguments():
    """
    Parse command line arguments
    """
    parser = argparse.ArgumentParser(description='UDP Client for latency measurement')
    parser.add_argument('--cloud-ip', type=str, required=True, help='Cloud server IP address')
    parser.add_argument('--mobile-ip', type=str, required=True, 
                        help='Mobile IP address to bind for UDP data communication (format: x.x.x.x)')
    parser.add_argument('--request-size', type=int, default=100, help='Request size in bytes (default: 10)')
    parser.add_argument('--response-size', type=int, default=100, help='Response size in bytes (default: 10)')
    parser.add_argument('--interval', type=int, default=1000, help='Request interval in ms (default: 1000)')
    parser.add_argument('--count', type=int, default=10, help='Number of requests to send (default: 10)')
    parser.add_argument('--timeout', type=int, default=1000, help='Socket timeout in ms (default: 1000)')
    parser.add_argument('--list-interfaces', action='store_true',
                        help='List available network interfaces and exit')
    parser.add_argument('--no-ping-pong', action='store_true',
                        help='Disable UDP ping-pong testing')
    
    return parser.parse_args()



def send_control_message(sock, server_address, request_size, response_size):
    """
    Send control message to server and wait for ACK
    
    Args:
        sock: UDP socket
        server_address: Server address tuple (ip, port)
        request_size: Size of request packets
        response_size: Size of response packets
    
    Returns:
        bool: True if ACK received successfully, False otherwise
    """
    try:
        # Pack control message: type(1) + request_size(4) + response_size(4)
        control_message = struct.pack('!BII', MSG_TYPE_CONTROL, request_size, response_size)
        
        # Send control message
        sock.sendto(control_message, server_address)
        print(f"Sent control message - Request size: {request_size}, Response size: {response_size}")
        
        # Wait for ACK
        data, _ = sock.recvfrom(MAX_UDP_PACKET)
        if len(data) >= 1 and data[0] == MSG_TYPE_CONTROL:
            print("Received control ACK")
            return True
        else:
            print("Received unexpected message type")
            return False
            
    except (socket.timeout, struct.error) as e:
        print(f"Error in control message: {e}")
        return False

def send_request(sock, server_address, request_size):
    """
    Send request data to server
    
    Args:
        sock: UDP socket
        server_address: Server address tuple (ip, port)
        request_size: Size of request data to send
    
    Returns:
        tuple: (request_id, send_time) if sent successfully, (None, None) otherwise
    """
    global request_counter
    try:
        # Generate a request ID
        request_id = request_counter
        request_counter += 1
        
        # Calculate header size: type(1) + request_id(4) + chunk_id(2) + total_chunks(2)
        header_size = 9
        
        # Calculate actual payload size
        payload_size = request_size - header_size
        if payload_size < 0:
            print(f"Error: Request size {request_size} is too small for header")
            return None, None
            
        # Calculate how many chunks we need
        max_chunk_payload = MAX_UDP_PACKET - header_size
        total_chunks = (payload_size + max_chunk_payload - 1) // max_chunk_payload
        total_chunks = max(1, total_chunks)  # At least 1 chunk
        
        print(f"Total request data length: {request_size} bytes, splitting into {total_chunks} chunks")
        
        # Split data into chunks and send
        remaining_payload = payload_size
        for chunk_id in range(total_chunks):
            # Calculate this chunk's payload size
            this_chunk_payload = min(max_chunk_payload, remaining_payload)
            
            # Pack the header: type(1) + request_id(4) + chunk_id(2) + total_chunks(2)
            chunk_header = struct.pack('!BIHH', MSG_TYPE_REQUEST, request_id, chunk_id, total_chunks)
            
            # Create chunk data with header and payload
            chunk_data = chunk_header + b'0' * this_chunk_payload
            
            # Send the chunk
            sock.sendto(chunk_data, server_address)
            print(f"Sent chunk {chunk_id+1}/{total_chunks} of request {request_id}: {len(chunk_data)} bytes")
            
            # Update remaining payload
            remaining_payload -= this_chunk_payload
            
        # Record start time just before sending first chunk
        send_time = time.time()
        
        return request_id, send_time
        
    except Exception as e:
        print(f"Error sending request: {e}")
        return None, None

def receive_response(sock, request_id, send_time, timeout_ms=5000):
    """
    Wait for and process response chunks for a specific request
    
    Args:
        sock: UDP socket
        request_id: Request ID to wait for response
        send_time: Time when the request was sent
        timeout_ms: Socket timeout in milliseconds
    
    Returns:
        tuple: (bool, float) - success status and RTT in ms
    """
    # Set timeout for receiving response
    original_timeout = sock.gettimeout()
    sock.settimeout(timeout_ms / 1000)  # Convert ms to seconds
    
    response_complete = False
    start_time = time.time()
    received_chunks = {}  # {chunk_id: True}
    total_chunks = None
    
    try:
        while time.time() - start_time < timeout_ms / 1000:  # Convert ms to seconds
            try:
                # Receive response data
                data, _ = sock.recvfrom(MAX_UDP_PACKET)
                
                # Ensure we have at least the header
                if len(data) < 9:  # type(1) + request_id(4) + chunk_id(2) + total_chunks(2)
                    print("Received too small response chunk")
                    continue
                
                # Unpack header to get type, request ID, chunk ID and total chunks
                msg_type, resp_request_id, chunk_id, chunks_count = struct.unpack('!BIHH', data[:9])
                
                if msg_type != MSG_TYPE_REQUEST:
                    print(f"Received unexpected message type: {msg_type}")
                    continue
                
                # Check if this response matches our request
                if resp_request_id == request_id:
                    # Record this chunk and update total chunks if needed
                    received_chunks[chunk_id] = True
                    if total_chunks is None:
                        total_chunks = chunks_count
                    print(f"Received response chunk {chunk_id+1}/{chunks_count} for request {request_id}")
                    
                    # Check if we have all chunks
                    if len(received_chunks) == total_chunks:
                        # Calculate RTT when all response chunks received
                        receive_complete_time = time.time()
                        rtt_ms = (receive_complete_time - send_time) * 1000  # Convert to ms
                        print(f"Received all {total_chunks} response chunks for request {request_id}")
                        response_complete = True
                        break
                else:
                    print(f"Received response for different request: {resp_request_id}")
            
            except socket.timeout:
                # Timeout on this receive, try again if within overall timeout
                pass
    
    except Exception as e:
        print(f"Error receiving response: {e}")
    
    finally:
        # Restore original timeout
        sock.settimeout(original_timeout)
    
    # Calculate RTT if response is complete
    if response_complete:
        return True, rtt_ms
    else:
        return False, None

def create_results_file(request_size, response_size):
    """Create results file with packet size information in the filename"""
    global results_file
    
    # Create timestamp for filename
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create results file with size information
    results_filename = f"rtt_req{request_size}_resp{response_size}_{timestamp}.txt"
    results_file = open(results_filename, "w")
    
    # Write header to results file with fixed-width format
    results_file.write(f"{'Request ID':<10s}  {'RTT (ms)':<12s}  {'Req Size':<10s}  {'Resp Size':<10s}\n")
    results_file.write("-" * 50 + "\n")
    
    print(f"Saving results to {results_filename}")
    return results_filename

def setup_udp_socket(mobile_ip=None):
    """Set up UDP socket for communication with server, binding to mobile IP if provided"""
    try:
        # Create UDP socket
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Bind to specific mobile IP if provided
        if mobile_ip:
            try:
                udp_socket.bind((mobile_ip, 0))  # 0 means any available port
                print(f"UDP socket bound to Mobile IP: {mobile_ip}")
            except Exception as bind_err:
                print(f"Failed to bind UDP socket to {mobile_ip}: {bind_err}")
                print("Continuing without binding to specific interface")
        
        return udp_socket
    except Exception as e:
        print(f"Failed to set up UDP socket: {e}")
        return None

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

def ping_pong_client(cloud_ip, mobile_ip=None):
    """
    Create UDP ping-pong measurement between client and server.
    One thread sends pings, another receives pongs.
    
    Args:
        cloud_ip: IP address of the cloud server
        mobile_ip: Optional mobile interface IP to bind to
    """
    global ping_sequence, ping_pong_socket
    
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
        server_address = (cloud_ip, PING_PONG_PORT)
        
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
    """
    Main function to start the client
    """
    global measurement_count, results_file, running, ping_pong_socket
    
    args = parse_arguments()
    
    # Check if list-interfaces was requested
    if args.list_interfaces:
        interfaces = get_local_interfaces()
        if interfaces:
            print("Available network interfaces:")
            for iface, ip in interfaces:
                print(f"  {iface}: {ip}")
            print("\nExample usage:")
            print(f"  python3 {os.path.basename(__file__)} --cloud-ip 192.168.1.100 --mobile-ip 10.0.0.5")
        else:
            print("No network interfaces found or unable to determine interfaces")
        return
    
    # Check if mobile IP is in available interfaces
    interfaces = get_local_interfaces()
    available_ips = [ip for _, ip in interfaces]
    
    if args.mobile_ip not in available_ips:
        print(f"Warning: Mobile IP {args.mobile_ip} not found in local network interfaces.")
        print("Available interfaces:")
        for iface, ip in interfaces:
            print(f"  {iface}: {ip}")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            print("Exiting...")
            return
    
    # Start ping-pong UDP latency testing if not disabled
    if not args.no_ping_pong:
        print(f"Starting UDP ping-pong testing to {args.cloud_ip} using interface {args.mobile_ip}")
        ping_pong_socket, _, _ = ping_pong_client(args.cloud_ip, args.mobile_ip)
    
    time.sleep(1)
    
    # Create UDP socket bound to mobile IP
    client_socket = setup_udp_socket(args.mobile_ip)
    if not client_socket:
        print("Failed to create UDP socket. Exiting...")
        return
    
    client_socket.settimeout(args.timeout / 1000)  # Convert ms to seconds
    
    server_address = (args.cloud_ip, UDP_PORT)
    
    try:
        # Send control message and wait for ACK
        if not send_control_message(client_socket, server_address, args.request_size, args.response_size):
            print("Failed to establish connection with server")
            return
            
        print("Connection established with server")
        
        # Create results file
        create_results_file(args.request_size, args.response_size)
        
        # Send requests and wait for responses
        successful_requests = 0
        for i in range(args.count):
            print(f"\nSending request {i+1}/{args.count}")
            request_id, send_time = send_request(client_socket, server_address, args.request_size)
            
            if request_id is None:
                print(f"Failed to send request {i+1}")
                continue
                
            # Wait for response if expected
            if args.response_size > 0:
                print(f"Waiting for response to request {request_id}...")
                response_received, rtt = receive_response(client_socket, request_id, send_time, args.timeout)
                
                if response_received:
                    successful_requests += 1
                    measurement_count += 1
                    print(f"Completed request-response cycle for request {i+1}")
                    if rtt is not None:
                        print(f"RTT: {rtt:.3f} ms")
                        
                        # Save results to file
                        if results_file:
                            results_file.write(f"{measurement_count:<10d}  {rtt:<12.3f}  {args.request_size:<10d}  {args.response_size:<10d}\n")
                            results_file.flush()  # Ensure data is written to disk
                            print(f"Saved measurement #{measurement_count} to file")
                else:
                    print(f"Response timeout for request {i+1}")
            
            # Wait for the specified interval before next request
            if i < args.count - 1:  # Don't wait after the last request
                print(f"Waiting {args.interval}ms before next request")
                time.sleep(args.interval / 1000)  # Convert ms to seconds
        
        print(f"\nSuccessfully completed {successful_requests}/{args.count} request-response cycles")
        
    except KeyboardInterrupt:
        print("\nClient shutting down...")
        running = False
    finally:
        # Close sockets
        client_socket.close()
        if ping_pong_socket:
            ping_pong_socket.close()
        
        # Close results file
        if results_file:
            results_file.close()
            results_filename = getattr(results_file, 'name', 'unknown')
            print(f"Results saved to {results_filename}")

if __name__ == "__main__":
    main()
