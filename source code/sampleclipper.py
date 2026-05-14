import cv2
import time

# Replace with your camera's RTSP URL or IP address stream
RTSP_URL = "rtsp://username:password@camera_ip:port/path"  # Update this with actual RTSP stream URL

# Duration of each clip in seconds
CLIP_DURATION = 10  
# Set clip counter to name files sequentially
clip_counter = 1  

def record_clip(duration, output_filename):
    # Open video capture from RTSP stream
    cap = cv2.VideoCapture(RTSP_URL)
    if not cap.isOpened():
        print("Error: Unable to open the video stream.")
        return

    # Get the frame rate to calculate the clip's total frames
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    frame_count = duration * fps

    # Define video codec and create VideoWriter object
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_filename, fourcc, fps, (frame_width, frame_height))

    print(f"Recording clip: {output_filename}")

    # Record for the specified duration
    for _ in range(frame_count):
        ret, frame = cap.read()
        if not ret:
            print("Error: Unable to read frame.")
            break
        out.write(frame)

    # Release everything once the recording is complete
    cap.release()
    out.release()
    print(f"Clip saved as: {output_filename}")

try:
    while True:
        # Define the output filename based on the clip counter
        output_filename = f"clip_{clip_counter}.mp4"
        record_clip(CLIP_DURATION, output_filename)
        
        # Increment the clip counter for the next file
        clip_counter += 1
        
        # Optional delay between clips if needed
        time.sleep(2)  # Adjust as needed

except KeyboardInterrupt:
    print("Recording stopped.")
