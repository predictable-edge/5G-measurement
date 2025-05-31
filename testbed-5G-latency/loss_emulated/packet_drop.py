#!/usr/bin/env python3
# xdp_burst_drop.py - XDP version burst packet drop program (warning-free)

from bcc import BPF
import sys
import time
import os

# Check arguments
if len(sys.argv) != 2:
    print(f"Usage: {sys.argv[0]} <interface_name>")
    print(f"Example: {sys.argv[0]} eth0")
    sys.exit(1)

device = sys.argv[1]

# Check sudo privileges
if os.geteuid() != 0:
    print("Error: sudo privileges required")
    sys.exit(1)

# XDP eBPF program (drops packets in receive direction)
prog = """
#include <uapi/linux/bpf.h>
#include <linux/if_ether.h>
#include <linux/ip.h>

BPF_ARRAY(drop_state, u32, 1);
BPF_ARRAY(stats, u64, 2);  // 0: total, 1: dropped

int xdp_drop(struct xdp_md *ctx) {
    u32 key = 0;
    u32 stats_key;  // Changed from u64 to u32 to match BPF_ARRAY index type
    
    // Update total packet count
    stats_key = 0;
    u64 *total = stats.lookup(&stats_key);
    if (total) (*total)++;
    
    u32 *drops = drop_state.lookup(&key);
    if (!drops) return XDP_PASS;
    
    // Currently in drop burst phase
    if (*drops > 0) {
        (*drops)--;
        
        // Update drop statistics
        stats_key = 1;
        u64 *dropped = stats.lookup(&stats_key);
        if (dropped) (*dropped)++;
        
        return XDP_DROP;
    }
    
    // 1% probability to trigger burst drop
    if (bpf_get_prandom_u32() % 20000 == 0) {
        u32 count = 50 + (bpf_get_prandom_u32() % 50);  // 50-100 packets
        drop_state.update(&key, &count);
        
        // Update drop statistics
        stats_key = 1;
        u64 *dropped = stats.lookup(&stats_key);
        if (dropped) (*dropped)++;
        
        return XDP_DROP;
    }
    
    return XDP_PASS;
}
"""

try:
    print("Loading XDP program...")
    b = BPF(text=prog, cflags=["-w"])  # Suppress compiler warnings
    fn = b.load_func("xdp_drop", BPF.XDP)
    
    print(f"Attaching to interface {device}...")
    b.attach_xdp(device, fn, 0)
    
    print(f"✓ XDP burst drop program loaded on {device}")
    print("  - Direction: Receive (RX)")
    print("  - Trigger probability: 0.1%")
    print("  - Drop count: 50-100 packets/burst")
    print(f"\nPress Ctrl+C to stop the program...\n")
    
    # Statistics
    stats = b.get_table("stats")
    drop_state = b.get_table("drop_state")
    
    last_total = 0
    last_dropped = 0
    
    while True:
        time.sleep(2)
        
        try:
            total = stats[0].value if 0 in stats else 0
            dropped = stats[1].value if 1 in stats else 0
            current_drops = drop_state[0].value if 0 in drop_state else 0
            
            total_diff = total - last_total
            dropped_diff = dropped - last_dropped
            
            drop_rate = (dropped_diff / total_diff * 100) if total_diff > 0 else 0
            
            print(f"Packet stats - Total: {total:8d} (+{total_diff:4d}) | "
                  f"Dropped: {dropped:6d} (+{dropped_diff:3d}) | "
                  f"Drop rate: {drop_rate:5.1f}% | "
                  f"Burst remaining: {current_drops:2d}")
            
            last_total = total
            last_dropped = dropped
            
        except Exception as e:
            print(f"Statistics read error: {e}")

except KeyboardInterrupt:
    print("\nUnloading program...")
    try:
        b.remove_xdp(device, 0)
        print("✓ XDP program unloaded")
    except:
        print("Error during unload, manual cleanup may be required")

except Exception as e:
    print(f"Error: {e}")
    print("\nTroubleshooting:")
    print("1. Ensure running with sudo privileges")
    print("2. Check interface name: ip link show")
    print("3. Install BCC: sudo apt-get install python3-bpfcc")
    print("4. Ensure kernel supports XDP")
    sys.exit(1)