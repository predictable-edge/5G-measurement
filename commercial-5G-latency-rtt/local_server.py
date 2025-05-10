#!/usr/bin/env python3
import socket
import time
import struct
import threading
import argparse
import datetime
import os

# Configuration
LISTEN_IP = '0.0.0.0'     # Listen on all interfaces for phone connection
LISTEN_PORT = 5001        # Port for receiving data from phone

# Global variables
rtt_lock = threading.Lock()      # Lock for thread-safe updates to data
running = True                  # Flag to control thread execution
measurement_count = 0           # Counter for received packets
results_file = None             # File to save measurement results
request_size = 0                # Size of request packets
response_size = 0               # Size of response packets

def handle_phone_client(client_socket, client_address):
    """Handle a phone client connection"""
    global measurement_count, results_file, request_size, response_size
    
    try:
        print(f"Phone connected from {client_address}")
        
        while running:
            try:
                # Receive RTT data: request_id(4) + rtt(8) + request_size(4) + response_size(4) = 20 bytes
                data = client_socket.recv(20)
                if not data or len(data) < 20:
                    if not data:
                        print("Connection closed by phone")
                    else:
                        print(f"Incomplete data received: {len(data)} bytes, expected 20 bytes")
                    break
                
                # Parse the data to get request ID, RTT, request size and response size
                original_request_id, rtt_ms, req_size, resp_size = struct.unpack('!IdII', data)
                
                # Update packet sizes - store the first valid values
                with rtt_lock:
                    if request_size == 0 and response_size == 0:
                        request_size = req_size
                        response_size = resp_size
                        
                        # Create new results file with size information if it wasn't created yet
                        if results_file is None:
                            create_results_file()
                
                # Increment measurement counter
                with rtt_lock:
                    measurement_count += 1
                
                print(f"Original request {original_request_id}: RTT = {rtt_ms:.3f} ms, Request size = {req_size}, Response size = {resp_size}")
                
                # Save results to file - using measurement_count as the request ID
                if results_file:
                    with rtt_lock:  # Use lock to avoid file corruption
                        results_file.write(f"{measurement_count:<10d}  {rtt_ms:<12.3f}  {req_size:<10d}  {resp_size:<10d}\n")
                        results_file.flush()  # Ensure data is written to disk
                
                print(f"Saved measurement #{measurement_count} to file")
                print("-" * 50)
                
            except socket.timeout:
                # Socket timeout, just continue the loop
                continue
            except Exception as e:
                print(f"Error receiving data: {e}")
                break
    
    except Exception as e:
        print(f"Error handling phone client {client_address}: {e}")
    finally:
        # Close the connection
        client_socket.close()
        print(f"Phone connection closed with {client_address}")

def create_results_file():
    """Create results file with packet size information in the filename"""
    global results_file, request_size, response_size
    
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

def listen_for_phone():
    """Listen for phone connections"""
    # Create TCP socket for phone communication
    phone_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    phone_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Disable Nagle algorithm
    phone_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    phone_socket.bind((LISTEN_IP, LISTEN_PORT))
    phone_socket.listen(5)  # Allow up to 5 queued connections
    
    print(f"Listening for phone connections on {LISTEN_IP}:{LISTEN_PORT}")
    
    try:
        while running:
            try:
                # Accept new connection
                client_socket, client_address = phone_socket.accept()
                
                # Start a new thread to handle this client
                client_thread = threading.Thread(
                    target=handle_phone_client,
                    args=(client_socket, client_address)
                )
                client_thread.daemon = True
                client_thread.start()
            except socket.timeout:
                # Socket timeout, just continue the loop
                continue
            except Exception as e:
                if running:  # Only log error if we're still supposed to be running
                    print(f"Error accepting connection: {e}")
                    time.sleep(1)  # Avoid tight loop if there's an error
    
    except Exception as e:
        print(f"Error in phone listener: {e}")
    finally:
        phone_socket.close()
        print("Phone listener shut down")

def main():
    global running, results_file, request_size, response_size
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Local server for RTT measurements')
    parser.add_argument('--port', type=int, default=LISTEN_PORT,
                        help=f'Port to listen on (default: {LISTEN_PORT})')
    args = parser.parse_args()
    
    try:
        # Start listening thread
        phone_listen_thread = threading.Thread(
            target=listen_for_phone, 
            daemon=True
        )
        phone_listen_thread.start()
        
        print(f"Local server running on port {args.port}")
        print("Press Ctrl+C to exit")
        
        # Keep the main thread running
        try:
            while running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("Exiting...")
            running = False
    finally:
        # Close results file
        if results_file:
            results_file.close()
            results_filename = getattr(results_file, 'name', 'unknown')
            print(f"Results saved to {results_filename}")

if __name__ == "__main__":
    main()
