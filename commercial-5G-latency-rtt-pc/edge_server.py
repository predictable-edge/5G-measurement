import socket
import struct
import time
import threading
from collections import defaultdict

# Maximum UDP packet size (practically safe)
MAX_UDP_PACKET = 1300
# UDP port for data communication
UDP_PORT = 5000
# Port for UDP ping-pong measurements
PING_PONG_PORT = 5001

# Message types
MSG_TYPE_CONTROL = 1
MSG_TYPE_REQUEST = 2

# Global variables
running = True              # Flag to control thread execution

# Storage for received chunks
chunk_buffer = defaultdict(dict)  # {request_id: {chunk_id: data}}

def receive_large_message(sock, expected_size, max_packet_size=MAX_UDP_PACKET, timeout=5):
    """
    Receive a large message that might be split across multiple datagrams
    
    Args:
        sock: UDP socket
        expected_size: Expected total size of the message
        max_packet_size: Maximum size of each datagram
        timeout: Timeout in seconds for receiving each datagram
    
    Returns:
        tuple: (message_data, client_address) or (None, None) if timeout
    """
    try:
        # Set timeout for receiving datagrams
        sock.settimeout(timeout)
        
        # Receive first datagram
        data, client_address = sock.recvfrom(max_packet_size)
        current_size = len(data)
        received_data = data
        
        # If message is complete in one datagram
        if current_size >= expected_size:
            return received_data, client_address
            
        # Receive remaining datagrams
        while current_size < expected_size:
            try:
                data, _ = sock.recvfrom(max_packet_size)
                received_data += data
                current_size += len(data)
            except socket.timeout:
                print("Timeout while receiving message fragments")
                return None, None
                
        return received_data, client_address
        
    except socket.timeout as e:
        print(f"Error receiving message: {e}")
        return None, None
    finally:
        # Reset timeout to None (blocking)
        sock.settimeout(None)

def process_chunk(data, client_address):
    """
    Process a received chunk of data
    
    Args:
        data: The received chunk data
        client_address: The client address (ip, port)
    
    Returns:
        tuple: (is_complete, request_id) if all chunks received, otherwise (False, request_id)
    """
    try:
        # Ensure we have at least the header
        if len(data) < 9:  # type(1) + request_id(4) + chunk_id(2) + total_chunks(2)
            print(f"Received too small chunk from {client_address}")
            return False, None
            
        # Unpack header: type(1) + request_id(4) + chunk_id(2) + total_chunks(2)
        try:
            msg_type, request_id, chunk_id, total_chunks = struct.unpack('!BIHH', data[:9])
        except struct.error as e:
            print(f"Error unpacking chunk header from {client_address}: {e}, data length: {len(data)}")
            return False, None
        
        if msg_type != MSG_TYPE_REQUEST:
            print(f"Received unexpected message type: {msg_type}")
            return False, None
        
        # Just record that we received this chunk - no need to store payload
        chunk_buffer[request_id][chunk_id] = True
        print(f"Received chunk {chunk_id+1}/{total_chunks} of request {request_id}")
        
        # Check if we have received all chunks
        if len(chunk_buffer[request_id]) == total_chunks:
            print(f"Received all chunks for request {request_id}")
            # Clear buffer for this request
            del chunk_buffer[request_id]
            return True, request_id
            
        return False, request_id
        
    except (IndexError) as e:
        print(f"Error processing chunk: {e}")
        return False, None

def clear_chunk_buffer():
    """
    Clear the chunk buffer
    """
    if chunk_buffer:
        chunk_buffer.clear()
        print("Cleared chunk buffer")

def send_response(sock, client_address, request_id, response_size):
    """
    Send response data to client
    
    Args:
        sock: UDP socket
        client_address: Client address tuple (ip, port)
        request_id: Request ID to respond to
        response_size: Size of response data to send
    
    Returns:
        bool: True if response sent successfully, False otherwise
    """
    try:
        # Calculate header size: type(1) + request_id(4) + chunk_id(2) + total_chunks(2)
        header_size = 9
        
        # Calculate actual payload size
        payload_size = response_size - header_size
        if payload_size < 0:
            print(f"Warning: Response size {response_size} is too small for header, adjusting")
            payload_size = 0
        
        # Calculate how many chunks we need
        max_chunk_payload = MAX_UDP_PACKET - header_size
        total_chunks = (payload_size + max_chunk_payload - 1) // max_chunk_payload
        total_chunks = max(1, total_chunks)  # At least 1 chunk
        
        print(f"Sending response for request {request_id}: {response_size} bytes in {total_chunks} chunks")
        
        # Split data into chunks and send
        remaining_payload = payload_size
        for chunk_id in range(total_chunks):
            # Calculate this chunk's payload size
            this_chunk_payload = min(max_chunk_payload, remaining_payload)
            
            # Pack the header: type(1) + request_id(4) + chunk_id(2) + total_chunks(2)
            # Use explicit ints to ensure correct type conversion across platforms
            chunk_header = struct.pack('!BIHH', int(MSG_TYPE_REQUEST), int(request_id), int(chunk_id), int(total_chunks))
            
            # Create chunk data with header and payload
            chunk_data = chunk_header + b'0' * this_chunk_payload
            
            # Send the chunk
            sock.sendto(chunk_data, client_address)
            print(f"Sent response chunk {chunk_id+1}/{total_chunks} for request {request_id}")
            time.sleep(0.000001)  # Sleep for 100 microseconds
            
            # Update remaining payload
            remaining_payload -= this_chunk_payload
            
        return True
            
    except Exception as e:
        print(f"Error sending response: {e}")
        return False

def handle_ping_pong_udp():
    """
    Handle ping-pong requests over UDP.
    Immediately responds to each ping message with a pong message.
    """
    try:
        # Create UDP socket for ping-pong
        ping_pong_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        ping_pong_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ping_pong_socket.bind(('', PING_PONG_PORT))
        
        print(f"Server listening for ping-pong requests on UDP port {PING_PONG_PORT}")
        
        pong_count = 0
        
        while running:
            # Receive ping request
            data, client_address = ping_pong_socket.recvfrom(1024)
            
            try:
                message = data.decode()
                
                # Handle PING message
                if message.startswith("PING:"):
                    # Extract sequence number
                    sequence = message.split(":")[1]
                    
                    # Create pong response with same sequence
                    response = f"PONG:{sequence}".encode()
                    
                    # Send response back to the client (same address that sent the ping)
                    ping_pong_socket.sendto(response, client_address)
                    
                    pong_count += 1
                    if pong_count % 100 == 0:
                        print(f"Sent {pong_count} pong responses")
                else:
                    print(f"Unexpected message format from {client_address}: {message}")
            
            except Exception as e:
                print(f"Error processing ping-pong message: {e}")
                continue
    
    except Exception as e:
        print(f"Error in ping-pong UDP handler: {e}")
    finally:
        if 'ping_pong_socket' in locals():
            ping_pong_socket.close()

def start_udp_server(port=UDP_PORT, max_packet_size=MAX_UDP_PACKET):
    """
    Start a UDP server that listens for incoming data
    
    Args:
        port (int): Port number to listen on
        max_packet_size (int): Maximum size of UDP packet to receive
    
    Returns:
        None
    """
    # Create UDP socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Bind the socket to the port
    server_address = ('', port)
    server_socket.bind(server_address)
    
    print(f"UDP Server listening on port {port}")
    
    # Dictionary to store client configurations
    client_configs = {}
    
    try:
        while True:
            # Wait for incoming data
            data, client_address = server_socket.recvfrom(max_packet_size)
            
            try:
                # Get message type from first byte
                msg_type = data[0]
                
                if msg_type == MSG_TYPE_CONTROL:
                    # Clear chunk buffer when control message is received
                    clear_chunk_buffer()
                    
                    # Unpack control message: type(1) + request_size(4) + response_size(4)
                    try:
                        _, request_size, response_size = struct.unpack('!BII', data)
                        print(f"Received control message - Request size: {request_size}, Response size: {response_size}")
                        
                        # Store client configuration
                        client_configs[client_address] = {
                            'request_size': request_size,
                            'response_size': response_size
                        }
                        
                        # Send control ACK (just the message type)
                        ack_message = struct.pack('!B', MSG_TYPE_CONTROL)
                        server_socket.sendto(ack_message, client_address)
                        print("Sent control ACK")
                    except struct.error as e:
                        print(f"Error unpacking control message from {client_address}: {e}")
                    
                elif msg_type == MSG_TYPE_REQUEST:
                    # Process the chunk
                    is_complete, request_id = process_chunk(data, client_address)
                    
                    # If request is complete and we have client config
                    if is_complete and client_address in client_configs:
                        response_size = client_configs[client_address]['response_size']
                        
                        # Send response if needed
                        if response_size > 0:
                            send_response(server_socket, client_address, request_id, response_size)
                
            except (IndexError) as e:
                print(f"Error processing message: {e}")
            
    except KeyboardInterrupt:
        print("\nServer shutting down...")
    finally:
        server_socket.close()

def main():
    """
    Main function to start the server
    """
    global running
    
    try:
        # Start ping-pong handler thread
        ping_pong_thread = threading.Thread(
            target=handle_ping_pong_udp,
            daemon=True
        )
        ping_pong_thread.start()
        
        # Start the main UDP server thread
        server_thread = threading.Thread(
            target=start_udp_server,
            daemon=True
        )
        server_thread.start()
        
        print("Server started. Press Ctrl+C to exit.")
        
        # Keep the main thread alive
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nServer shutting down...")
        running = False
        time.sleep(1)  # Give threads time to clean up

if __name__ == "__main__":
    main()
