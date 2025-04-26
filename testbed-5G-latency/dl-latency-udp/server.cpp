#include <iostream>
#include <string>
#include <cstring>
#include <chrono>
#include <vector>
#include <thread>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>

#define MAX_PACKET_SIZE 1400

// Packet structure
struct Packet {
    uint64_t timestamp;  // Timestamp when packet is sent
    uint32_t packet_id;  // ID of this packet
    uint32_t total_packets;  // Total number of packets in this request
    uint32_t request_id;  // Request ID
    uint32_t total_requests;  // Total number of requests to be sent
    uint32_t data_size;  // Size of actual data in this packet
    char data[MAX_PACKET_SIZE];  // Data buffer
};

// Function to send a single request
void send_request(int sockfd, const sockaddr_in& client_addr, int bytes_to_send, int request_id, int total_requests) {
    // Calculate how many packets we need
    int total_packets = (bytes_to_send + MAX_PACKET_SIZE - 1) / MAX_PACKET_SIZE;
    int bytes_remaining = bytes_to_send;
    
    std::vector<Packet> packets(total_packets);
    
    // Prepare all packets
    for (int i = 0; i < total_packets; i++) {
        packets[i].packet_id = i;
        packets[i].total_packets = total_packets;
        packets[i].request_id = request_id;
        packets[i].total_requests = total_requests;
        
        // Determine data size for this packet
        packets[i].data_size = (bytes_remaining > MAX_PACKET_SIZE) ? MAX_PACKET_SIZE : bytes_remaining;
        bytes_remaining -= packets[i].data_size;
        
        // Fill data with pattern for testing
        for (uint32_t j = 0; j < packets[i].data_size; j++) {
            packets[i].data[j] = 'A' + (j % 26);
        }
    }
    
    // Send all packets
    for (int i = 0; i < total_packets; i++) {
        // Get current timestamp right before sending
        packets[i].timestamp = std::chrono::duration_cast<std::chrono::microseconds>(
            std::chrono::system_clock::now().time_since_epoch()
        ).count();
        
        // Send the packet
        sendto(sockfd, &packets[i], sizeof(Packet), 0, 
               (struct sockaddr*)&client_addr, sizeof(client_addr));
        
        std::cout << "Sent packet " << i+1 << "/" << total_packets 
                  << " of request " << request_id 
                  << " with timestamp " << packets[i].timestamp 
                  << " and size " << packets[i].data_size << " bytes" << std::endl;
    }
}

int main(int argc, char* argv[]) {
    if (argc < 5) {
        std::cerr << "Usage: " << argv[0] << " <target_ip> <target_port> <bytes_to_send> <num_requests> [send_interval_ms]" << std::endl;
        return 1;
    }
    
    // Parse command line arguments
    std::string target_ip = argv[1];
    int target_port = std::stoi(argv[2]);
    int bytes_to_send = std::stoi(argv[3]);
    int num_requests = std::stoi(argv[4]);
    int send_interval_ms = (argc > 5) ? std::stoi(argv[5]) : 1000;  // Default 1000ms interval
    
    // Create UDP socket
    int sockfd = socket(AF_INET, SOCK_DGRAM, 0);
    if (sockfd < 0) {
        std::cerr << "Error creating socket" << std::endl;
        return 1;
    }
    
    // Set up client address
    struct sockaddr_in client_addr;
    memset(&client_addr, 0, sizeof(client_addr));
    client_addr.sin_family = AF_INET;
    client_addr.sin_port = htons(target_port);
    
    if (inet_pton(AF_INET, target_ip.c_str(), &client_addr.sin_addr) <= 0) {
        std::cerr << "Invalid address/ Address not supported" << std::endl;
        close(sockfd);
        return 1;
    }
    
    std::cout << "Server starting to send " << num_requests << " requests of " 
              << bytes_to_send << " bytes each to " << target_ip << ":" << target_port 
              << " with interval " << send_interval_ms << "ms" << std::endl;
    
    // Send requests
    for (int i = 0; i < num_requests; i++) {
        std::cout << "Sending request " << i+1 << "/" << num_requests << std::endl;
        send_request(sockfd, client_addr, bytes_to_send, i, num_requests);
        
        // Wait for the interval before sending next request
        if (i < num_requests - 1) {
            std::this_thread::sleep_for(std::chrono::milliseconds(send_interval_ms));
        }
    }
    
    std::cout << "All requests sent successfully" << std::endl;
    close(sockfd);
    return 0;
}
