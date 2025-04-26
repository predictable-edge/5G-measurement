#include <iostream>
#include <fstream>
#include <string>
#include <cstring>
#include <chrono>
#include <map>
#include <vector>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <iomanip>
#include <signal.h>

#define MAX_PACKET_SIZE 1400

// Packet structure - must match the server's structure
struct Packet {
    uint64_t timestamp;  // Timestamp when packet is sent
    uint32_t packet_id;  // ID of this packet
    uint32_t total_packets;  // Total number of packets in this request
    uint32_t request_id;  // Request ID
    uint32_t total_requests;  // Total number of requests to be sent
    uint32_t data_size;  // Size of actual data in this packet
    char data[MAX_PACKET_SIZE];  // Data buffer
};

// Structure to track statistics for each request
struct RequestStats {
    uint64_t first_packet_send_time = 0;
    uint64_t first_packet_recv_time = 0;
    uint64_t last_packet_recv_time = 0;
    bool is_complete = false;
    std::map<int, bool> received_packets;
};

// Global variables for signal handler
bool running = true;
std::map<int, RequestStats> requests;
std::string output_file;

// Signal handler for graceful shutdown
void signal_handler(int signal) {
    std::cout << "Received signal " << signal << ", shutting down..." << std::endl;
    running = false;
}

// Function to write results to file
void write_results() {
    std::ofstream outfile(output_file);
    if (!outfile.is_open()) {
        std::cerr << "Error opening output file: " << output_file << std::endl;
        return;
    }
    
    // Write header
    outfile << std::left << std::setw(15) << "Request_ID" 
            << std::setw(30) << "First_Packet_Latency(us)" 
            << std::setw(30) << "Last_to_First_Packet_Diff(us)" 
            << "\n";
    
    // Write data for each request
    for (const auto& pair : requests) {
        uint32_t request_id = pair.first;
        const RequestStats& stats = pair.second;
        
        uint64_t first_packet_latency = stats.first_packet_recv_time - stats.first_packet_send_time;
        uint64_t last_to_first_diff = stats.last_packet_recv_time - stats.first_packet_recv_time;
        
        outfile << std::left << std::setw(15) << request_id
                << std::setw(30) << first_packet_latency
                << std::setw(30) << last_to_first_diff
                << "\n";
    }
    
    outfile.close();
    std::cout << "Results written to " << output_file << std::endl;
}

int main(int argc, char* argv[]) {
    if (argc < 3) {
        std::cerr << "Usage: " << argv[0] << " <listen_port> <output_file>" << std::endl;
        return 1;
    }
    
    // Parse command line arguments
    int listen_port = std::stoi(argv[1]);
    output_file = argv[2];
    
    // Set up signal handler
    signal(SIGINT, signal_handler);
    
    // Create UDP socket
    int sockfd = socket(AF_INET, SOCK_DGRAM, 0);
    if (sockfd < 0) {
        std::cerr << "Error creating socket" << std::endl;
        return 1;
    }
    
    // Set socket timeout
    struct timeval tv;
    tv.tv_sec = 0;
    tv.tv_usec = 500000;  // 500ms timeout
    if (setsockopt(sockfd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv)) < 0) {
        std::cerr << "Error setting socket timeout" << std::endl;
        close(sockfd);
        return 1;
    }
    
    // Set up server address
    struct sockaddr_in server_addr;
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port = htons(listen_port);
    
    // Bind socket to address
    if (bind(sockfd, (struct sockaddr*)&server_addr, sizeof(server_addr)) < 0) {
        std::cerr << "Error binding socket to port " << listen_port << std::endl;
        close(sockfd);
        return 1;
    }
    
    std::cout << "Client listening on port " << listen_port << std::endl;
    std::cout << "Press Ctrl+C to stop and write results to file" << std::endl;
    std::cout << "Client will also automatically terminate after receiving all expected requests" << std::endl;
    
    Packet packet;
    struct sockaddr_in client_addr;
    socklen_t client_len = sizeof(client_addr);
    uint32_t highest_request_id = 0;
    uint32_t total_requests = 0;  // Will be set by received packets
    
    // Receive packets
    while (running) {
        int bytes_received = recvfrom(sockfd, &packet, sizeof(Packet), 0, 
                                     (struct sockaddr*)&client_addr, &client_len);
        
        if (bytes_received < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                // Timeout occurred, just continue and check running flag
                continue;
            }
            std::cerr << "Error receiving packet: " << strerror(errno) << std::endl;
            continue;
        }
        
        // Get current timestamp when packet is received
        uint64_t recv_time = std::chrono::duration_cast<std::chrono::microseconds>(
            std::chrono::system_clock::now().time_since_epoch()
        ).count();
        
        // Process the received packet
        uint32_t request_id = packet.request_id;
        uint32_t packet_id = packet.packet_id;
        uint32_t total_packets = packet.total_packets;
        
        // Update total requests if needed
        if (total_requests == 0 || packet.total_requests > total_requests) {
            total_requests = packet.total_requests;
            std::cout << "Total requests expected: " << total_requests << std::endl;
        }
        
        // Update highest request ID seen
        if (request_id > highest_request_id) {
            highest_request_id = request_id;
        }
        
        std::cout << "Received packet " << packet_id+1 << "/" << total_packets 
                  << " of request " << request_id << "/" << total_requests
                  << " with timestamp " << packet.timestamp
                  << " and size " << packet.data_size << " bytes" << std::endl;
        
        // Initialize this request if it's the first time we're seeing it
        if (requests.find(request_id) == requests.end()) {
            requests[request_id] = RequestStats();
        }
        
        // Record that we've received this packet
        requests[request_id].received_packets[packet_id] = true;
        
        // If this is the first packet of the request
        if (packet_id == 0) {
            requests[request_id].first_packet_send_time = packet.timestamp;
            requests[request_id].first_packet_recv_time = recv_time;
        }
        
        // Update the last packet receive time
        requests[request_id].last_packet_recv_time = recv_time;
        
        // Check if the request is complete
        if (requests[request_id].received_packets.size() == static_cast<size_t>(total_packets)) {
            requests[request_id].is_complete = true;
            std::cout << "Request " << request_id << " completed" << std::endl;
        }
        
        // Check if we have received all requests and all packets for each request
        if (total_requests > 0 && highest_request_id == total_requests - 1) {
            bool all_complete = true;
            for (uint32_t i = 0; i < total_requests; i++) {
                if (requests.find(i) == requests.end() || !requests[i].is_complete) {
                    all_complete = false;
                    break;
                }
            }
            
            if (all_complete) {
                std::cout << "All " << total_requests << " requests completed. Terminating..." << std::endl;
                running = false;
            }
        }
        
        // Write intermediate results every 10 requests
        if (request_id % 10 == 9) {
            write_results();
        }
    }
    
    close(sockfd);
    
    // Write final results to file
    write_results();
    
    return 0;
}
