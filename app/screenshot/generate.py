#!/usr/bin/env python3
"""
Video Frame Extractor - Extracts frames from videos at timestamps recorded in a JSONL file.
"""

import argparse
import cv2
import json
import logging
import os
from typing import List, Optional

import requests


class TimestampExtractor:
    """Handles extraction of relevant timestamps from event logs."""
    
    @staticmethod
    def format_timestamp_to_hms(timestamp: float) -> str:
        """Convert a float timestamp in seconds to HH:MM:SS.mmm format."""
        hours = int(timestamp // 3600)
        minutes = int((timestamp % 3600) // 60)
        seconds = int(timestamp % 60)
        milliseconds = int((timestamp % 1) * 1000)
        return f"{hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03}"
    
    @staticmethod
    def parse_hms_to_milliseconds(timestamp: str) -> Optional[float]:
        """Convert HH:MM:SS.mmm format to milliseconds."""
        try:
            parts = timestamp.split(":")
            if len(parts) != 3:
                logging.warning(f"Invalid timestamp format: {timestamp}")
                return None
                
            hours, minutes, seconds = map(float, parts)
            return (hours * 3600 + minutes * 60 + seconds) * 1000
        except ValueError as e:
            logging.error(f"Error parsing timestamp {timestamp}: {e}")
            return None

    def extract_click_timestamps(self, jsonl_file: str) -> List[str]:
        """
        Extract left-click timestamps from a remote JSONL file relative to the first event.
        
        Args:
            jsonl_file: URL to the JSONL log file
            
        Returns:
            List of timestamps in HH:MM:SS.mmm format
        """
        timestamps = []

        try:
            # Check if the input is a URL
            if jsonl_file.startswith("http://") or jsonl_file.startswith("https://"):
                response = requests.get(jsonl_file)
                response.raise_for_status()
                lines = response.text.splitlines()
            else:
                # Read local file if not a URL
                with open(jsonl_file, "r") as file:
                    lines = file.readlines()

            # Get base timestamp from first line
            first_line = lines[0].strip() if lines else None
            if not first_line:
                logging.error("Empty JSONL file")
                return []
                
            first_event = json.loads(first_line)
            first_timestamp = first_event.get("time_stamp")
            if first_timestamp is None:
                logging.error("First line missing time_stamp field")
                return []

            # Process each subsequent line
            for line_num, line in enumerate(lines[1:], 2):  # Start counting from line 2
                line = line.strip()
                if not line:
                    continue
                    
                try:
                    event = json.loads(line)

                    # Check for left-click events when the button is pressed
                    if event.get("pressed", False) and event.get("button") == "left":
                        current_timestamp = event.get("time_stamp")
                        if current_timestamp is None:
                            logging.warning(f"Missing time_stamp in line {line_num}")
                            continue

                        relative_timestamp = max(0.0, current_timestamp - first_timestamp)
                        formatted_time = self.format_timestamp_to_hms(relative_timestamp)
                        timestamps.append(formatted_time)
                except json.JSONDecodeError:
                    logging.warning(f"Invalid JSON in line {line_num}")

        except requests.RequestException as e:
            logging.error(f"Error fetching JSONL from URL: {e}")
        except FileNotFoundError:
            logging.error(f"File not found: {jsonl_file}")
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON in the first line of {jsonl_file}")
        except Exception as e:
            logging.error(f"Error processing JSONL file: {e}")

        logging.info(f"Found {len(timestamps)} click events")
        return timestamps


class VideoFrameExtractor:
    """Handles extraction of frames from video files at specified timestamps."""
    
    def __init__(self, video_file: str, output_dir: str):
        """
        Initialize the frame extractor.
        
        Args:
            video_file: Path to the video file
            output_dir: Directory to save extracted frames
        """
        self.video_file = video_file
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self._cap = None
        
    def __enter__(self):
        """Context manager entry - opens the video file."""
        self._cap = cv2.VideoCapture(self.video_file)
        if not self._cap.isOpened():
            logging.error(f"Cannot open video file: {self.video_file}")
            self._cap.release()
            self._cap = None
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures video capture is released."""
        if self._cap:
            self._cap.release()
            self._cap = None
        
    def extract_frames(self, timestamps: List[str]) -> int:
        """
        Extract frames from the video at the given timestamps.
        
        Args:
            timestamps: List of timestamps in HH:MM:SS.mmm format
            
        Returns:
            Number of successfully extracted frames
        """
        if not timestamps:
            logging.warning("No timestamps provided for extraction")
            return 0
            
        # Open video if not already opened by context manager
        needs_cleanup = False
        if not self._cap:
            self._cap = cv2.VideoCapture(self.video_file)
            needs_cleanup = True
            
        if not self._cap or not self._cap.isOpened():
            logging.error(f"Cannot open video file: {self.video_file}")
            return 0

        extracted_count = 0
        timestamp_extractor = TimestampExtractor()
        
        try:
            for idx, timestamp in enumerate(timestamps):
                milliseconds = timestamp_extractor.parse_hms_to_milliseconds(timestamp)
                if milliseconds is None:
                    continue
                    
                # Set video position and read frame
                self._cap.set(cv2.CAP_PROP_POS_MSEC, milliseconds)
                success, frame = self._cap.read()
                
                if success:
                    # Create a safe filename with timestamp
                    safe_timestamp = timestamp.replace(':', '_')
                    output_path = os.path.join(
                        self.output_dir, 
                        f"frame_{idx+1}_{safe_timestamp}.png"
                    )
                    
                    # Save the frame and immediately release memory
                    cv2.imwrite(output_path, frame)
                    # Explicitly clear the frame from memory
                    del frame
                    
                    extracted_count += 1
                    logging.debug(f"Extracted frame at {timestamp} to {output_path}")
                else:
                    logging.warning(f"Failed to retrieve frame at {timestamp}")
        finally:
            # Only release if we created the capture in this method
            if needs_cleanup and self._cap:
                self._cap.release()
                self._cap = None
            
        logging.info(f"Extracted {extracted_count} of {len(timestamps)} frames")
        return extracted_count


def process_video(video_file: str, jsonl_file: str, output_dir: str) -> None:
    """
    Main processing function to extract frames from video based on JSONL events.
    
    Args:
        video_file: Path to the video file
        jsonl_file: Path to the JSONL event log file
        output_dir: Directory to save extracted frames
    """
    # Extract timestamps from the JSONL file
    timestamp_extractor = TimestampExtractor()
    timestamps = timestamp_extractor.extract_click_timestamps(jsonl_file)
    
    if not timestamps:
        logging.warning("No valid timestamps found in the JSONL file")
        return
        
    # Extract frames at the identified timestamps using context manager
    # to ensure proper resource cleanup
    with VideoFrameExtractor(video_file, output_dir) as frame_extractor:
        frame_extractor.extract_frames(timestamps)
    
    # delete the output directory if empty
    if os.listdir(output_dir):
        os.rmdir(output_dir)
        logging.info(f"Deleted output Directory: {output_dir}")


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Extract video frames at timestamps from JSONL event log"
    )
    parser.add_argument("--video", "-v", default="./google_lens.mp4",
                        help="Path to video file")
    parser.add_argument("--jsonl", "-j", default="events.jsonl",
                        help="Path to JSONL event log file")
    parser.add_argument("--output", "-o", default="output_frames",
                        help="Output directory for extracted frames")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable verbose logging")
    parser.add_argument("--memory-limit", type=int, default=0,
                        help="Set OpenCV memory buffer limit in MB (0 = default)")
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_arguments()
    
    # Set up logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    # Configure OpenCV memory limits if specified
    if args.memory_limit > 0:
        logging.info(f"Setting OpenCV memory limit to {args.memory_limit}MB")
        # Convert MB to bytes for cv2
        cv2.setUseOptimized(True)
        if hasattr(cv2, 'setBufferPoolUsage'):  # Only in newer OpenCV versions
            cv2.setBufferPoolUsage(True)
        
    logging.info(f"Processing video: {args.video}")
    logging.info(f"Using events from: {args.jsonl}")
    logging.info(f"Saving frames to: {args.output}")
    
    try:
        process_video(args.video, args.jsonl, args.output)
        logging.info("Processing complete")
    except Exception as e:
        logging.error(f"Unhandled exception: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return 1
    finally:
        # Force garbage collection to clean up any lingering resources
        import gc
        gc.collect()
        
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())