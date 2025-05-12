#!/usr/bin/env python3
import socket
import time
import struct
import threading
import argparse

# Configuration
AWS_SERVER_DATA_PORT = 5002     # Port for data communication
LOCAL_SERVER_IP = '127.0.0.1'   # Local server IP address
LOCAL_SERVER_PORT = 5001        # Local server port for data forwarding
MAX_UDP_SEGMENT = 4096          # Maximum UDP segment size
UDP_BUFFER_SIZE = 4194304       # Buffer size for UDP socket (4MB)
TIMEOUT_SEC = 1                # Timeout for UDP operations

# Global variables
aws_data_socket = None          # UDP socket for AWS server
local_server_socket = None      # UDP socket for local server communication
local_server_addr = None        # Local server address tuple
running = True                  # Flag to control thread execution

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

def setup_aws_data_socket(aws_server_ip):
    """Set up UDP socket for communication with AWS server"""
    global aws_data_socket
    
    try:
        # Create UDP socket
        aws_data_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Set buffer sizes
        aws_data_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, UDP_BUFFER_SIZE)
        aws_data_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, UDP_BUFFER_SIZE)
        
        # Set timeout
        aws_data_socket.settimeout(TIMEOUT_SEC)
        
        # Store server address
        aws_server_address = (aws_server_ip, AWS_SERVER_DATA_PORT)
        
        print(f"Set up UDP socket for AWS data server at {aws_server_ip}:{AWS_SERVER_DATA_PORT}")
        return aws_server_address
    except Exception as e:
        print(f"Failed to set up UDP socket for AWS data server: {e}")
        return None

def connect_to_local_server(local_ip):
    """Set up UDP socket for communication with local server"""
    global local_server_socket, local_server_addr
    
    try:
        # Create UDP socket
        local_server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Set buffer sizes
        try:
            # Use smaller UDP buffer (8KB)
            local_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8192)
            cur_sndbuf = local_server_socket.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
            print(f"UDP send buffer size set to: {cur_sndbuf} bytes")
        except Exception as e:
            print(f"Could not set UDP buffer size: {e}")
        
        # Set timeout
        local_server_socket.settimeout(TIMEOUT_SEC)
        
        # Store server address
        local_server_addr = (local_ip, LOCAL_SERVER_PORT)
        
        print(f"Set up UDP socket for local server at {local_ip}:{LOCAL_SERVER_PORT}")
        return True
    except Exception as e:
        print(f"Failed to set up UDP socket for local server: {e}")
        return False

def receive_data_from_server_udp(aws_server_address, num_requests, interval_ms, bytes_per_request):
    """Receive data from AWS server using UDP"""
    global aws_data_socket, local_server_socket, local_server_addr, running
    
    try:
        # Send parameters to server
        # num_requests, interval_ms, bytes_per_request
        params = struct.pack('!iii', num_requests, interval_ms, bytes_per_request)
        aws_data_socket.sendto(params, aws_server_address)
        
        print(f"Sent parameters to server: requests={num_requests}, interval={interval_ms}ms, bytes={bytes_per_request}")
        
        # Wait for acknowledgment with timeout
        try:
            ack, server_addr = aws_data_socket.recvfrom(MAX_UDP_SEGMENT)
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
            aws_data_socket.sendto(b'TRIG', aws_server_address)
            print(f"Sent trigger packet for request {request_count+1}/{num_requests}")
            
            try:
                # First receive the header which contains request ID, timestamp, packet size, and total segments
                # Format: !IdII = 4-byte int (request ID) + 8-byte double + 4-byte unsigned int + 4-byte unsigned int = 20 bytes total
                header, server_addr = aws_data_socket.recvfrom(MAX_UDP_SEGMENT)
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
                    flush_udp_buffer(aws_data_socket)  # Flush all pending packets
                    request_count += 1
                    continue
                
                # Record the time when header is received
                receive_time = time.time()
                print(f"receive_time: {receive_time}")
                
                # Output timestamps without correction
                print(f"Request {request_id}: Local timestamp: {receive_time:.6f}, Server timestamp: {server_timestamp:.6f}")
                print(f"Time difference: {(receive_time - server_timestamp)*1000:.2f} ms")
                
                # Forward header to local server
                if local_server_socket and local_server_addr:
                    try:
                        # Calculate time difference in ms
                        time_diff_ms = (receive_time - server_timestamp) * 1000
                        
                        # Reformat header for local server (which now expects 20 bytes: timestamp, size, and time diff)
                        local_header = struct.pack('!dId', server_timestamp, packet_size, time_diff_ms)
                        local_server_socket.sendto(local_header, local_server_addr)
                        print(f"Forwarded header to local server: {len(local_header)} bytes (including time diff: {time_diff_ms:.2f} ms)")
                    except Exception as e:
                        print(f"Error forwarding header to local server: {e}")
                
                # Now receive the payload data in segments
                received_packet = bytearray()
                segments_received = 0
                
                while segments_received < total_segments and running and len(received_packet) < packet_size:
                    try:
                        segment, addr = aws_data_socket.recvfrom(MAX_UDP_SEGMENT)
                        
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
                        flush_udp_buffer(aws_data_socket)
                        break
                
                # If we received all segments
                if segments_received == total_segments:
                    if len(received_packet) == packet_size:
                        request_count += 1
                        packet_receive_time = time.time()
                        duration_ms = (packet_receive_time - receive_time) * 1000
                        print(f"Packet fully received for request ID {request_id}. Duration: {duration_ms:.2f} ms, Packet size: {packet_size} bytes")
                        
                        # Send duration to local server
                        if local_server_socket and local_server_addr:
                            try:
                                # Pack duration as a double (8 bytes)
                                duration_bytes = struct.pack('d', duration_ms)
                                local_server_socket.sendto(duration_bytes, local_server_addr)
                                print(f"Sent reception duration to local server: {duration_ms:.2f} ms")
                            except Exception as e:
                                print(f"Error sending duration to local server: {e}")
                        
                        print("-" * 50)
                    else:
                        print(f"Packet size mismatch for request ID {request_id}: received {len(received_packet)} bytes, expected {packet_size} bytes")
                        flush_udp_buffer(aws_data_socket)  # Flush on error
                else:
                    print(f"Incomplete packet for request ID {request_id}: received {segments_received}/{total_segments} segments")
                    flush_udp_buffer(aws_data_socket)  # Flush on incomplete segments
                    
            except socket.timeout:
                print(f"Timeout waiting for response for request {request_count+1}")
                flush_udp_buffer(aws_data_socket)  # Flush on timeout
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
    global aws_data_socket, local_server_socket, local_server_addr, running
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='UDP Phone client for latency decomposition')
    parser.add_argument('--aws-ip', dest='aws_server_ip', required=True,
                        help='IP address of the AWS server')
    parser.add_argument('--local-ip', dest='local_server_ip', default=LOCAL_SERVER_IP,
                        help=f'IP address of the local server (default: {LOCAL_SERVER_IP})')
    parser.add_argument('--requests', type=int, default=100,
                        help='Number of requests to receive (default: 100)')
    parser.add_argument('--interval', type=int, default=1000,
                        help='Interval between requests in milliseconds (default: 1000)')
    parser.add_argument('--bytes', type=int, default=0,
                        help='Number of bytes per request (default: 0)')
    args = parser.parse_args()
    
    try:
        # Set up UDP socket for AWS server
        aws_server_address = setup_aws_data_socket(args.aws_server_ip)
        if not aws_server_address:
            print("Failed to set up UDP socket for AWS server, exiting...")
            running = False
            return
        
        # Connect to local server for data forwarding (UDP)
        connect_to_local_server(args.local_server_ip)
        # Continue even if local server connection fails
        
        # Start data reception
        receive_data_from_server_udp(aws_server_address, args.requests, args.interval, args.bytes)
        
    except KeyboardInterrupt:
        print("Exiting...")
        running = False
    finally:
        # Close sockets
        if aws_data_socket:
            aws_data_socket.close()
        if local_server_socket:
            local_server_socket.close()

if __name__ == "__main__":
    main()
