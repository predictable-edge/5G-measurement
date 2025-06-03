#!/usr/bin/env python3
"""
Normal Distribution CPU Load Stressor using stress-ng
Runs on Ubuntu 22, adjusting CPU load every 100ms following normal distribution
"""

import subprocess
import time
import signal
import sys
import argparse
import random
import math
import threading
import os
import psutil
from datetime import datetime
from typing import Optional, List

class StressNGController:
    """Controller for stress-ng processes with normal distribution load patterns"""
    
    def __init__(self, mean_load: float = 50, std_load: float = 15, 
                 interval: float = 0.1, num_cores: int = 0, verbose: bool = True,
                 monitor_cpu: bool = False):
        """
        Initialize the stress-ng controller
        
        Args:
            mean_load: Mean CPU load percentage (0-100)
            std_load: Standard deviation of CPU load percentage
            interval: Load adjustment interval in seconds
            num_cores: Number of CPU cores to use (0 = auto-detect)
            verbose: Enable verbose output
            monitor_cpu: Enable real-time CPU monitoring (may affect timing)
        """
        self.mean_load = mean_load
        self.std_load = std_load
        self.interval = interval
        self.num_cores = num_cores if num_cores > 0 else psutil.cpu_count()
        self.verbose = verbose
        self.monitor_cpu = monitor_cpu
        
        self.running = False
        self.stress_process: Optional[subprocess.Popen] = None
        self.controller_thread: Optional[threading.Thread] = None
        self.monitor_thread: Optional[threading.Thread] = None
        self.current_load = 0.0
        self.actual_cpu_usage = 0.0
        self.iteration_count = 0
        
        # Register signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Validate dependencies
        self._check_dependencies()
        
    def _signal_handler(self, signum: int, frame) -> None:
        """Handle termination signals"""
        if self.verbose:
            print(f"\nReceived signal {signum}, stopping...")
        self.stop()
        sys.exit(0)
        
    def _check_dependencies(self) -> None:
        """Check if required dependencies are available"""
        try:
            result = subprocess.run(['stress-ng', '--version'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                raise subprocess.CalledProcessError(result.returncode, 'stress-ng')
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            print("Error: stress-ng not found. Please install: sudo apt install stress-ng")
            sys.exit(1)
            
    def _generate_normal_load(self) -> float:
        """Generate a normally distributed load value using Box-Muller transform"""
        # Box-Muller transform for normal distribution
        u1 = random.random()
        u2 = random.random()
        
        # Avoid log(0)
        while u1 == 0:
            u1 = random.random()
            
        z0 = math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)
        load = self.mean_load + self.std_load * z0
        
        # Clamp to valid range
        return max(0.0, min(100.0, load))
    
    def _start_stress_ng(self, load_percentage: float) -> bool:
        """Start stress-ng process with specified load"""
        try:
            # Kill any existing stress-ng processes
            self._stop_stress_ng()
            
            # Build stress-ng command
            cmd = [
                'stress-ng',
                '--cpu', str(self.num_cores),
                '--cpu-load', str(int(round(load_percentage))),
                '--quiet'
            ]
            
            # Start new stress-ng process
            self.stress_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid  # Create new process group for clean termination
            )
            
            return True
            
        except Exception as e:
            if self.verbose:
                print(f"Error starting stress-ng: {e}")
            return False
    
    def _stop_stress_ng(self) -> None:
        """Stop current stress-ng process"""
        if self.stress_process and self.stress_process.poll() is None:
            try:
                # Send SIGTERM to process group
                os.killpg(os.getpgid(self.stress_process.pid), signal.SIGTERM)
                
                # Wait for process to terminate
                try:
                    self.stress_process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't terminate gracefully
                    os.killpg(os.getpgid(self.stress_process.pid), signal.SIGKILL)
                    self.stress_process.wait()
                    
            except (OSError, ProcessLookupError):
                pass  # Process already terminated
            finally:
                self.stress_process = None
        
        # Additional cleanup: kill any remaining stress-ng processes
        try:
            subprocess.run(['pkill', '-f', 'stress-ng.*--cpu-load'], 
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            pass
    
    def _get_cpu_usage(self) -> float:
        """Get current CPU usage percentage"""
        try:
            # Use longer interval for more accurate measurement
            return psutil.cpu_percent(interval=0.5)
        except:
            return 0.0
    
    def _cpu_monitor_loop(self) -> None:
        """Separate thread for CPU monitoring to avoid affecting timing"""
        if self.verbose:
            print("CPU monitor thread started")
            
        while self.running:
            try:
                if self.stress_process and self.stress_process.poll() is None:
                    # Use longer interval for accurate measurement
                    self.actual_cpu_usage = psutil.cpu_percent(interval=1.0)
                else:
                    self.actual_cpu_usage = 0.0
                time.sleep(0.5)  # Update every 0.5 seconds
            except Exception as e:
                if self.verbose:
                    print(f"Error in CPU monitor: {e}")
                time.sleep(1.0)
                
        if self.verbose:
            print("CPU monitor thread stopped")
    
    def _controller_loop(self) -> None:
        """Main controller loop that adjusts load based on normal distribution"""
        if self.verbose:
            print("Load controller thread started")
            
        while self.running:
            try:
                start_time = time.time()
                
                # Generate new load value
                new_load = self._generate_normal_load()
                self.current_load = new_load
                self.iteration_count += 1
                
                # Apply new load
                success = self._start_stress_ng(new_load)
                
                # Display status
                if self.verbose and success:
                    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    if self.monitor_cpu:
                        print(f"[{timestamp}] Iteration {self.iteration_count:4d} | "
                              f"Target: {new_load:5.1f}% | Actual: {self.actual_cpu_usage:5.1f}% | "
                              f"Cores: {self.num_cores}")
                    else:
                        print(f"[{timestamp}] Iteration {self.iteration_count:4d} | "
                              f"Target Load: {new_load:5.1f}% | Cores: {self.num_cores}")
                
                # Precise timing control
                elapsed = time.time() - start_time
                sleep_time = max(0, self.interval - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
            except Exception as e:
                if self.verbose:
                    print(f"Error in controller loop: {e}")
                time.sleep(self.interval)
                
        if self.verbose:
            print("Load controller thread stopped")
    
    def start(self, duration: float = 0) -> None:
        """
        Start the stress test
        
        Args:
            duration: Test duration in seconds (0 = infinite)
        """
        if self.running:
            print("Stress test is already running")
            return
            
        if self.verbose:
            print("=" * 70)
            print("Normal Distribution CPU Load Stressor using stress-ng")
            print("=" * 70)
            print(f"Target load distribution: Mean={self.mean_load}%, StdDev={self.std_load}%")
            print(f"Load adjustment interval: {self.interval*1000:.0f}ms")
            print(f"CPU cores used: {self.num_cores}")
            print(f"CPU monitoring: {'Enabled' if self.monitor_cpu else 'Disabled (use htop/top for monitoring)'}")
            if duration > 0:
                print(f"Test duration: {duration} seconds")
            else:
                print("Test duration: Unlimited")
            print("Press Ctrl+C to stop the test")
            print("=" * 70)
            print()
        
        self.running = True
        
        # Start CPU monitor thread if enabled
        if self.monitor_cpu:
            self.monitor_thread = threading.Thread(target=self._cpu_monitor_loop, daemon=True)
            self.monitor_thread.start()
        
        # Start controller thread
        self.controller_thread = threading.Thread(target=self._controller_loop, daemon=True)
        self.controller_thread.start()
        
        # Main thread waits for completion or signal
        try:
            if duration > 0:
                time.sleep(duration)
                if self.verbose:
                    print(f"\nTest duration completed ({duration} seconds)")
                self.stop()
            else:
                # Wait indefinitely
                while self.running:
                    time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self) -> None:
        """Stop the stress test"""
        if not self.running:
            return
            
        if self.verbose:
            print("\nStopping CPU stress test...")
            
        self.running = False
        
        # Stop stress-ng process
        self._stop_stress_ng()
        
        # Wait for controller thread to finish
        if self.controller_thread and self.controller_thread.is_alive():
            self.controller_thread.join(timeout=2.0)
            
        # Wait for monitor thread to finish
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2.0)
        
        if self.verbose:
            print("CPU stress test stopped")
            print(f"Total iterations completed: {self.iteration_count}")
    
    def get_statistics(self) -> dict:
        """Get current test statistics"""
        return {
            'iteration_count': self.iteration_count,
            'current_load': self.current_load,
            'actual_cpu_usage': self.actual_cpu_usage if self.monitor_cpu else None,
            'mean_load': self.mean_load,
            'std_load': self.std_load,
            'interval': self.interval,
            'num_cores': self.num_cores,
            'running': self.running,
            'monitor_cpu': self.monitor_cpu
        }

def main():
    """Main function with command line interface"""
    parser = argparse.ArgumentParser(
        description='Normal Distribution CPU Load Stressor using stress-ng',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Use default parameters
  %(prog)s -m 80 -s 10 -i 0.1               # 80%% mean, 10%% std, 100ms interval  
  %(prog)s -m 60 -s 20 -c 4 -t 300          # 4 cores, run for 5 minutes
  %(prog)s --mean 70 --std 15 --quiet       # Quiet mode
  %(prog)s --monitor-cpu                     # Enable real-time CPU monitoring

Dependencies:
  - stress-ng (sudo apt install stress-ng)
  - psutil (pip3 install psutil)

Note:
  - Run as normal user (not root)
  - Use htop or top in another terminal for accurate CPU monitoring
  - --monitor-cpu option may affect timing precision
  - Press Ctrl+C to stop the test
        """)
    
    parser.add_argument('-m', '--mean', type=float, default=50,
                        help='Mean CPU load percentage (0-100, default: 50)')
    parser.add_argument('-s', '--std', type=float, default=15,
                        help='Standard deviation of CPU load percentage (default: 15)')
    parser.add_argument('-i', '--interval', type=float, default=1,
                        help='Load adjustment interval in seconds (default: 1)')
    parser.add_argument('-c', '--cores', type=int, default=0,
                        help='Number of CPU cores to use (0=auto-detect, default: 0)')
    parser.add_argument('-t', '--time', type=float, default=0,
                        help='Test duration in seconds (0=unlimited, default: 0)')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='Quiet mode - reduce output')
    parser.add_argument('--monitor-cpu', action='store_true',
                        help='Enable real-time CPU monitoring (may affect timing precision)')
    parser.add_argument('--seed', type=int, default=None,
                        help='Random seed for reproducible results')
    
    args = parser.parse_args()
    
    # Validate parameters
    if not 0 <= args.mean <= 100:
        print("Error: Mean load must be between 0 and 100")
        sys.exit(1)
        
    if args.std < 0:
        print("Error: Standard deviation must be >= 0")
        sys.exit(1)
        
    if args.interval <= 0:
        print("Error: Interval must be > 0")
        sys.exit(1)
        
    if args.cores < 0:
        print("Error: Number of cores must be >= 0")
        sys.exit(1)
        
    if args.time < 0:
        print("Error: Test duration must be >= 0")
        sys.exit(1)
    
    # Set random seed if provided
    if args.seed is not None:
        random.seed(args.seed)
        if not args.quiet:
            print(f"Using random seed: {args.seed}")
    
    # Check for root user (removed confirmation for automated use)
    # if os.geteuid() == 0:
    #     print("Warning: Running as root is not recommended")
    #     print("Press Enter to continue or Ctrl+C to cancel...")
    #     try:
    #         input()
    #     except KeyboardInterrupt:
    #         sys.exit(0)
    
    # Check dependencies
    try:
        import psutil
    except ImportError:
        print("Error: psutil not found. Please install: pip3 install psutil")
        sys.exit(1)
    
    # Create and run stress controller
    controller = StressNGController(
        mean_load=args.mean,
        std_load=args.std,
        interval=args.interval,
        num_cores=args.cores,
        verbose=not args.quiet,
        monitor_cpu=args.monitor_cpu
    )
    
    try:
        controller.start(duration=args.time)
    except Exception as e:
        print(f"Error: {e}")
        controller.stop()
        sys.exit(1)

if __name__ == "__main__":
    main()