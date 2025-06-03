#!/usr/bin/env python3
"""
FFprobe Frame Analyzer
This script runs ffprobe to extract frame information from a video file,
adds frame indices, and outputs frame index with packet size.
"""

import subprocess
import sys
import re
import argparse


def run_ffprobe(video_file):
    """
    Run ffprobe command to extract frame information from video file.
    
    Args:
        video_file (str): Path to the video file
        
    Returns:
        str: Raw output from ffprobe command
    """
    cmd = [
        'ffprobe',
        '-select_streams', 'v:0',
        '-show_frames',
        '-show_entries', 'frame=coded_picture_number,pkt_size,pict_type',
        '-of', 'default=noprint_wrappers=1:nokey=0',
        video_file
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error running ffprobe: {e}", file=sys.stderr)
        print(f"stderr: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("Error: ffprobe not found. Please make sure FFmpeg is installed.", file=sys.stderr)
        sys.exit(1)


def parse_frame_data(ffprobe_output):
    """
    Parse ffprobe output to extract frame packet sizes and picture types.
    
    Args:
        ffprobe_output (str): Raw output from ffprobe
        
    Returns:
        list: List of tuples containing (frame_index, packet_size, picture_type)
    """
    frames = []
    frame_index = 0
    current_pkt_size = None
    current_pict_type = None
    
    lines = ffprobe_output.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        
        # Skip empty lines and header information
        if not line or line.startswith('ffprobe') or line.startswith('Input #') or \
           line.startswith('Metadata:') or line.startswith('Duration:') or \
           line.startswith('Stream #') or line.startswith('handler_name') or \
           line.startswith('vendor_id') or line.startswith('major_brand') or \
           line.startswith('minor_version') or line.startswith('compatible_brands') or \
           line.startswith('encoder') or line.startswith('libav') or \
           line.startswith('built with') or line.startswith('configuration'):
            continue
            
        # Parse packet size
        if line.startswith('pkt_size='):
            # If we have previous frame data, save it
            if current_pkt_size is not None and current_pict_type is not None:
                frames.append((frame_index, current_pkt_size, current_pict_type))
                frame_index += 1
                current_pict_type = None  # Reset for next frame
            
            current_pkt_size = int(line.split('=')[1])
            
        # Parse picture type
        elif line.startswith('pict_type='):
            current_pict_type = line.split('=')[1]
            
        # Skip side_data_type and other metadata lines
        elif line.startswith('side_data_type='):
            continue
    
    # Don't forget the last frame if it exists
    if current_pkt_size is not None and current_pict_type is not None:
        frames.append((frame_index, current_pkt_size, current_pict_type))
    
    return frames


def print_frame_info(frames):
    """
    Print frame information in a formatted way.
    
    Args:
        frames (list): List of tuples containing frame data
    """
    print("Frame Index | Packet Size (bytes) | Picture Type")
    print("-" * 50)
    
    for frame_idx, pkt_size, pict_type in frames:
        print(f"{frame_idx:10d} | {pkt_size:18d} | {pict_type:11s}")


def main():
    """
    Main function to handle command line arguments and coordinate the analysis.
    """
    parser = argparse.ArgumentParser(
        description='Analyze video frames using ffprobe and add frame indices'
    )
    parser.add_argument(
        'video_file',
        help='Path to the video file to analyze'
    )
    parser.add_argument(
        '--csv',
        action='store_true',
        help='Output in CSV format'
    )
    
    args = parser.parse_args()
    
    # Check if video file exists
    import os
    if not os.path.exists(args.video_file):
        print(f"Error: Video file '{args.video_file}' not found.", file=sys.stderr)
        sys.exit(1)
    
    # Run ffprobe and get output
    print(f"Analyzing video file: {args.video_file}", file=sys.stderr)
    ffprobe_output = run_ffprobe(args.video_file)
    
    # Parse frame data
    frames = parse_frame_data(ffprobe_output)
    
    if not frames:
        print("No frame data found in ffprobe output.", file=sys.stderr)
        sys.exit(1)
    
    # Output results
    if args.csv:
        print("frame_index,packet_size,picture_type")
        for frame_idx, pkt_size, pict_type in frames:
            print(f"{frame_idx},{pkt_size},{pict_type}")
    else:
        print_frame_info(frames)
    
    print(f"\nTotal frames analyzed: {len(frames)}", file=sys.stderr)


if __name__ == "__main__":
    main()