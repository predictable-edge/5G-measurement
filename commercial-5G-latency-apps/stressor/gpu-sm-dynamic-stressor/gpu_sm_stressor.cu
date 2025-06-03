#include <cuda_runtime.h>
#include <cuda.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <signal.h>
#include <time.h>
#include <sys/time.h>
#include <chrono>
#include <thread>

static volatile int keep_running = 1;

void signal_handler(int sig) {
    keep_running = 0;
    printf("\nStopping GPU stress test...\n");
}

// GPU workload kernel - enhanced version to fully utilize SMs
__global__ void gpu_stress_kernel(float *data, int size, int iterations) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    int stride = blockDim.x * gridDim.x;
    
    // Ensure each thread has sufficient work
    for (int i = idx; i < size; i += stride) {
        float temp = data[i];
        
        // Execute intensive floating-point operations
        for (int iter = 0; iter < iterations; iter++) {
            temp = temp * 1.000001f + 0.000001f;
            temp = sqrtf(temp * temp + 1.0f);
            temp = sinf(temp) * cosf(temp);
            temp = expf(temp * 0.00001f);
            temp = logf(temp + 1.0f);
            temp = powf(temp, 1.001f);
        }
        
        data[i] = temp;
    }
}

// Print GPU device information
void print_gpu_info() {
    int device_count;
    cudaGetDeviceCount(&device_count);
    
    printf("Detected %d GPU device(s)\n", device_count);
    
    for (int i = 0; i < device_count; i++) {
        cudaDeviceProp prop;
        cudaGetDeviceProperties(&prop, i);
        
        printf("\nGPU %d: %s\n", i, prop.name);
        printf("  SM Count: %d\n", prop.multiProcessorCount);
        printf("  Max Threads/SM: %d\n", prop.maxThreadsPerMultiProcessor);
        printf("  Max Threads/Block: %d\n", prop.maxThreadsPerBlock);
        printf("  Max Blocks/SM: %d\n", prop.maxBlocksPerMultiProcessor);
        printf("  Global Memory: %.1f GB\n", prop.totalGlobalMem / (1024.0*1024.0*1024.0));
        printf("  Compute Capability: %d.%d\n", prop.major, prop.minor);
    }
}

// Get timestamp in milliseconds
long long get_timestamp_ms() {
    auto now = std::chrono::high_resolution_clock::now();
    auto duration = now.time_since_epoch();
    return std::chrono::duration_cast<std::chrono::milliseconds>(duration).count();
}

// Precise sleep function (milliseconds)
void precise_sleep_ms(int ms) {
    if (ms <= 0) return;
    std::this_thread::sleep_for(std::chrono::milliseconds(ms));
}

int main(int argc, char *argv[]) {
    if (argc != 2) {
        printf("Usage: %s <GPU_usage_percentage(0-100)>\n", argv[0]);
        printf("Example: %s 50  # Use 50%% of GPU SM\n", argv[0]);
        return 1;
    }
    
    float target_usage = atof(argv[1]);
    if (target_usage < 0 || target_usage > 100) {
        printf("Error: GPU usage percentage must be between 0-100\n");
        return 1;
    }
    
    // Register signal handlers
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    
    // Initialize CUDA
    cudaSetDevice(0);
    print_gpu_info();
    
    // Get GPU properties
    cudaDeviceProp prop;
    cudaGetDeviceProperties(&prop, 0);
    
    int sm_count = prop.multiProcessorCount;
    
    printf("\nStarting GPU stress test, target usage: %.1f%%\n", target_usage);
    printf("Using time-slicing method for precise GPU usage control\n");
    printf("Press Ctrl+C to stop the test\n\n");
    
    // Calculate time-slicing parameters
    int cycle_time_ms = 100;  // 100ms per cycle
    int work_time_ms = (int)(cycle_time_ms * target_usage / 100.0);
    int idle_time_ms = cycle_time_ms - work_time_ms;
    
    printf("Time-slicing configuration:\n");
    printf("  Cycle time: %d ms\n", cycle_time_ms);
    printf("  Work time: %d ms (%.1f%%)\n", work_time_ms, (float)work_time_ms/cycle_time_ms*100);
    printf("  Idle time: %d ms (%.1f%%)\n", idle_time_ms, (float)idle_time_ms/cycle_time_ms*100);
    printf("\n");
    
    // Configure kernel parameters - fully utilize GPU
    int threads_per_block = 512;
    int blocks_per_sm = 2;  // 2 blocks per SM
    int total_blocks = sm_count * blocks_per_sm;
    int total_threads = total_blocks * threads_per_block;
    
    printf("Kernel configuration:\n");
    printf("  Block count: %d\n", total_blocks);
    printf("  Threads per block: %d\n", threads_per_block);
    printf("  Total threads: %d\n", total_threads);
    printf("  Data size: %d MB\n\n", (int)(total_threads * sizeof(float) / (1024*1024)));
    
    // Allocate GPU memory
    float *d_data;
    size_t data_size = total_threads * sizeof(float);
    cudaMalloc(&d_data, data_size);
    
    // Initialize data
    float *h_data = (float*)malloc(data_size);
    for (int i = 0; i < total_threads; i++) {
        h_data[i] = (float)(i % 1000) / 1000.0f;
    }
    cudaMemcpy(d_data, h_data, data_size, cudaMemcpyHostToDevice);
    
    // Calculate kernel iterations to ensure full GPU load during work time
    int kernel_iterations = 5000;
    
    // Statistics
    long long start_time = get_timestamp_ms();
    long long last_print_time = start_time;
    int cycle_count = 0;
    long long total_work_time = 0;
    long long total_idle_time = 0;
    
    printf("Starting test loop...\n");
    
    while (keep_running) {
        long long cycle_start = get_timestamp_ms();
        
        // Work phase - launch GPU kernel
        if (work_time_ms > 0) {
            long long work_start = get_timestamp_ms();
            
            // Continuously launch kernels until work time is reached
            while (keep_running && (get_timestamp_ms() - work_start) < work_time_ms) {
                gpu_stress_kernel<<<total_blocks, threads_per_block>>>(
                    d_data, total_threads, kernel_iterations);
                cudaDeviceSynchronize();
            }
            
            total_work_time += get_timestamp_ms() - work_start;
        }
        
        // Idle phase - CPU sleep
        if (idle_time_ms > 0 && keep_running) {
            long long idle_start = get_timestamp_ms();
            precise_sleep_ms(idle_time_ms);
            total_idle_time += get_timestamp_ms() - idle_start;
        }
        
        cycle_count++;
        
        // Print statistics every second
        long long current_time = get_timestamp_ms();
        if (current_time - last_print_time >= 1000) {
            long long elapsed = current_time - start_time;
            float actual_usage = total_work_time * 100.0f / (total_work_time + total_idle_time);
            float cycles_per_sec = cycle_count * 1000.0f / elapsed;
            
            printf("\rTime: %llds | Cycles: %d | Actual usage: %.1f%% | Target: %.1f%% | Cycles/sec: %.1f", 
                   elapsed/1000, cycle_count, actual_usage, target_usage, cycles_per_sec);
            fflush(stdout);
            
            last_print_time = current_time;
        }
    }
    
    // Final statistics
    long long total_elapsed = get_timestamp_ms() - start_time;
    float final_usage = total_work_time * 100.0f / total_elapsed;
    
    printf("\n\n=== Test Complete ===\n");
    printf("Total runtime: %.1f seconds\n", total_elapsed / 1000.0f);
    printf("Total cycles: %d\n", cycle_count);
    printf("Actual GPU usage: %.1f%%\n", final_usage);
    printf("Target usage: %.1f%%\n", target_usage);
    printf("Error: %.1f%%\n", fabs(final_usage - target_usage));
    
    // Cleanup resources
    cudaFree(d_data);
    free(h_data);
    
    return 0;
}