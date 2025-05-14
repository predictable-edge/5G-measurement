#!/usr/bin/env python3
import socket
import time
import struct
import threading
import argparse

# Configuration
LOCAL_SERVER_IP = '127.0.0.1'   # Local server IP address
LOCAL_SERVER_PORT = 5001        # Local server port for data connection via UDP
AWS_SERVER_UDP_PORT = 5002      # AWS server UDP port for data transmission
MAX_UDP_SEGMENT = 4096          # Maximum UDP segment size

# Global variables
local_udp_socket = None         # UDP socket for local server communication
aws_udp_socket = None           # UDP socket for AWS server communication
running = True                  # Flag to control thread execution
aws_server_ip = None            # AWS server IP address

def setup_local_udp_socket():
    """Set up UDP socket for communication with local server"""
    global local_udp_socket
    
    try:
        # Create UDP socket
        local_udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        print(f"Set up UDP socket for local server communication")
        return True
    except Exception as e:
        print(f"Failed to set up UDP socket for local server: {e}")
        return False

def register_with_local_server(local_ip):
    """Register with local server via UDP"""
    global local_udp_socket
    
    if local_udp_socket is None:
        print("UDP socket not set up")
        return False
    
    try:
        # Create local server address
        local_address = (local_ip, LOCAL_SERVER_PORT)
        
        # Send registration message
        local_udp_socket.sendto(b'REGISTER', local_address)
        print(f"Sent registration to local server at {local_ip}:{LOCAL_SERVER_PORT}")
        
        # Wait for acknowledgment
        local_udp_socket.settimeout(5)  # 5-second timeout
        try:
            data, addr = local_udp_socket.recvfrom(1024)
            if data == b'ACK':
                print(f"Registration acknowledged by local server at {addr}")
                # Reset timeout to non-blocking for receiving data
                local_udp_socket.settimeout(None)
                return True
            else:
                print(f"Unexpected response from local server: {data}")
                return False
        except socket.timeout:
            print(f"Timeout waiting for acknowledgment from local server")
            return False
        
    except Exception as e:
        print(f"Failed to register with local server: {e}")
        return False

def setup_aws_udp_socket():
    """Set up UDP socket for communication with AWS server"""
    global aws_udp_socket
    
    try:
        # Create UDP socket
        aws_udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        print(f"Set up UDP socket for AWS server communication")
        return True
    except Exception as e:
        print(f"Failed to set up UDP socket: {e}")
        return False

def send_data_to_aws(request_id, request_size, server_timestamp):
    """Send data to AWS server over UDP"""
    global aws_udp_socket, aws_server_ip
    
    if aws_udp_socket is None or aws_server_ip is None:
        print("AWS socket or server IP not set up")
        return False
    
    try:
        # Create header with request_id, server_timestamp
        # Format: !Id = 4-byte unsigned int + 8-byte double = 12 bytes total
        header = struct.pack('!IdI', request_id, server_timestamp, request_size)
        
        # Create destination address
        aws_address = (aws_server_ip, AWS_SERVER_UDP_PORT)
        
        # Send header to AWS server
        aws_udp_socket.sendto(header, aws_address)
        print(f"Sent header to AWS server - Request ID: {request_id}, Server timestamp: {server_timestamp:.6f}")
        
        # Create payload of specified size
        payload = b'\x00' * request_size
        
        # Split payload into segments if needed
        segments_sent = 0
        total_segments = (request_size + MAX_UDP_SEGMENT - 5) // (MAX_UDP_SEGMENT - 4) if request_size > 0 else 0
        
        for i in range(0, request_size, MAX_UDP_SEGMENT - 4):
            # Get segment size
            segment_end = min(i + MAX_UDP_SEGMENT - 4, request_size)
            
            # Get the segment data
            segment_data = payload[i:segment_end]
            
            # Add request ID to each segment (4 bytes)
            segment = struct.pack('!I', request_id) + segment_data
            
            # Send segment
            aws_udp_socket.sendto(segment, aws_address)
            segments_sent += 1
            
            if segments_sent % 10 == 0 or segments_sent == total_segments:
                print(f"Sent segment {segments_sent}/{total_segments} to AWS server")
        
        print(f"Completed sending data to AWS server - Request ID: {request_id}, Size: {request_size} bytes in {segments_sent} segments")
        return True
        
    except Exception as e:
        print(f"Error sending data to AWS server: {e}")
        return False

def receive_data_from_local_server():
    """Continuously receive data from local server via UDP"""
    global local_udp_socket, running
    
    data_count = 0
    
    try:
        while running:
            try:
                # Receive data from local server
                data, addr = local_udp_socket.recvfrom(1024)
                
                # Check that we received enough data for a header
                if len(data) < 16:
                    print(f"Incomplete header received: {len(data)} bytes, expected at least 16 bytes")
                    continue
                
                # Parse header - first 16 bytes are the header
                # Header: request_id (4 bytes), size (4 bytes), timestamp (8 bytes)
                request_id, request_size, server_timestamp = struct.unpack('!IId', data[:16])
                
                data_count += 1
                print(f"Received packet {data_count} from local server - Request ID: {request_id}, Server timestamp: {server_timestamp:.6f}")
                
                # Forward data to AWS server
                send_data_to_aws(request_id, request_size, server_timestamp)
                
            except Exception as e:
                print(f"Error receiving data from local server: {e}")
                break
    
    except Exception as e:
        print(f"Error in data reception thread: {e}")
    finally:
        print(f"Data reception thread exited, received {data_count} packets total")

def main():
    global local_udp_socket, aws_udp_socket, running, aws_server_ip
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Phone client for latency decomposition')
    parser.add_argument('--local-ip', dest='local_server_ip', default=LOCAL_SERVER_IP,
                        help=f'IP address of the local server (default: {LOCAL_SERVER_IP})')
    parser.add_argument('--aws-ip', dest='aws_server_ip', required=True,
                        help='IP address of the AWS server')
    args = parser.parse_args()
    
    # Store AWS server IP
    aws_server_ip = args.aws_server_ip
    
    try:
        # Set up UDP socket for AWS server communication
        if not setup_aws_udp_socket():
            print("Failed to set up UDP socket for AWS server, exiting...")
            running = False
            return
            
        # Set up UDP socket for local server
        if not setup_local_udp_socket():
            print("Failed to set up UDP socket for local server, exiting...")
            running = False
            return
        
        # Register with local server
        if not register_with_local_server(args.local_server_ip):
            print("Failed to register with local server, exiting...")
            running = False
            return
        
        # Start data reception thread
        reception_thread = threading.Thread(target=receive_data_from_local_server)
        reception_thread.daemon = True
        reception_thread.start()
        
        print(f"Phone client running. Registered with local server and ready to forward data to AWS server at {aws_server_ip}:{AWS_SERVER_UDP_PORT}")
        print("Press Ctrl+C to exit.")
        
        # Keep the main thread running
        try:
            while running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("Exiting...")
            running = False
        
    finally:
        # Close sockets
        if local_udp_socket:
            local_udp_socket.close()
        if aws_udp_socket:
            aws_udp_socket.close()

if __name__ == "__main__":
    main()
