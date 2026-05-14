import numpy as np
import time
import ctypes
import subprocess
from scipy.signal import butter, lfilter
import os

# ================================================ Load WaveForms SDK ================================================
dwf = ctypes.CDLL("/Library/Frameworks/dwf.framework/dwf")

# ================================================ Parameters ================================================
SAMPLE_RATE = 250_000   # 250 kHz
BUFFER_SIZE = 16384     # Match WaveForms settings
PULSE_DURATION = 10     # Monitor for 10 seconds
ORDER = 4               # Order of the bandpass filter
LOG_INTERVAL = 0.01     # Log data every 0.01 seconds
THRESHOLD_DBV = -57     # Threshold for logging timestamps, *CHANGE FOR TESTING*

# RTSP stream URLs for both cameras, from IPcams app *they need to be connect to the same network as the computer*
# RTSP0 = "rtsp://10.10.10.20:554/user=admin_password=MKWuzQOe_channel=1_stream=0&onvif=0.sdp?real_st"
RTSP0 = "rtsp://10.10.10.22:554/user=admin_password=MKWuzQOe_channel=1_stream=0&onvif=0.sdp?real_st"

# Frequency ranges per person
PEOPLE = {
    # "Cole": (35000, 39000),
    # "Cami": (16500, 19000),
    "Omar": (35000, 40000),
}

# Track threshold crossings
swim_ins = {name: 0 for name in PEOPLE}
last_crossed = {name: False for name in PEOPLE}
recording_active = {name: False for name in PEOPLE}  # Track if recording is active

# Initialize a counter for recordings
recording_counters = {name: 0 for name in PEOPLE}

# ================================================ Initialize AD2 ================================================
def open_device():
    print("here1")
    hdwf = ctypes.c_int()
    dwf.FDwfDeviceOpen(ctypes.c_int(-1), ctypes.byref(hdwf))
    if hdwf.value == 0:
        print("Failed to open AD2 device.")
        return None
    return hdwf

def close_device(hdwf):
    dwf.FDwfDeviceClose(hdwf)

# ================================================ Configure AD2 analog input ================================================
def configure_device(hdwf):
    dwf.FDwfAnalogInChannelEnableSet(hdwf, ctypes.c_int(0), ctypes.c_int(1))   # Enable CH1
    dwf.FDwfAnalogInFrequencySet(hdwf, ctypes.c_double(SAMPLE_RATE))           # Set sample rate
    dwf.FDwfAnalogInBufferSizeSet(hdwf, ctypes.c_int(BUFFER_SIZE))             # Set buffer size
    dwf.FDwfAnalogInConfigure(hdwf, ctypes.c_bool(False), ctypes.c_bool(True)) # Start acquisition

# ================================================ Read data from AD2 ================================================
def read_data(hdwf):
    data = (ctypes.c_double * BUFFER_SIZE)()                                            # Allocate buffer
    dwf.FDwfAnalogInStatus(hdwf, ctypes.c_bool(True), None)
    dwf.FDwfAnalogInStatusData(hdwf, ctypes.c_int(0), data, ctypes.c_int(BUFFER_SIZE))
    return np.array(data)                                                               # Convert to numpy array for processing

#=================================================== Bandpass Filter ================================================
def butter_bandpass(lowcut, highcut, fs, order=5):
    nyq = 0.5 * fs
    low = lowcut / nyq                              # Normalize low cutoff
    high = highcut / nyq                            # Normalize high cutoff
    b, a = butter(order, [low, high], btype='band') # Get filter coefficients
    return b, a

def butter_bandpass_filter(data, lowcut, highcut, fs, order=5):
    b, a = butter_bandpass(lowcut, highcut, fs, order=order)
    y = lfilter(b, a, data)                                     # Apply filter to signal
    return y

# ================================================ Camera Recording Function using ffmpeg ================================================
def rec_clip_continuous(output_filename):
    command = [
        "ffmpeg",
        "-rtsp_transport", "tcp",
        "-y",
        "-i", RTSP0,  # First input stream
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-t", "60",  # Record for a long duration, we will clip later
        output_filename
    ]

    print("Recording continuously...")
    process = subprocess.Popen(command)
    return process

# ================================================ Main Loop ================================================
print("Current working directory:", os.getcwd())
hdwf = open_device()
print("here")
if hdwf:
    configure_device(hdwf)
    start_time = time.time()
    last_log_time = start_time
    collecting = True
    print("Starting data acquisition...")

    # Modify the main loop to handle continuous recording
    continuous_recording_process = None

    while True:
        current_time = time.time()
        
        # Skip processing for the first 3 seconds
        if current_time - start_time < 3:
            continue  # Skip the rest of the loop for the first 3 seconds

        # Toggle collecting every LOG_INTERVAL (creates a duty cycle to reduce CPU load)
        if collecting and current_time - last_log_time >= LOG_INTERVAL:
            last_log_time = current_time
            collecting = False  # Switch off for 1 interval
        elif not collecting and current_time - last_log_time >= LOG_INTERVAL:
            last_log_time = current_time
            collecting = True  # Switch back on
        
        if collecting:
            data = read_data(hdwf)

            for name, (low, high) in PEOPLE.items():

                # Bandpass filter for this person's frequency band
                filtered_data = butter_bandpass_filter(data, low, high, SAMPLE_RATE, order=ORDER)

                # Apply windowing to reduce spectral leakage before FFT
                window = np.blackman(len(filtered_data))
                windowed = filtered_data * window
                correction_factor = np.sum(window) / len(filtered_data)

                # Compute FFT and convert to dBV
                fft_result = np.fft.rfft(windowed) / (BUFFER_SIZE * correction_factor)
                magnitudes = 20 * np.log10(np.abs(fft_result) + 1e-12)

                # Get the frequencies corresponding to FFT bins
                freqs = np.fft.rfftfreq(len(filtered_data), 1 / SAMPLE_RATE)
                target_idx = np.where((freqs >= low) & (freqs <= high))[0]

                if len(target_idx) > 0:
                    peak_dbv = np.max(magnitudes[target_idx])
                    timestamp = current_time - start_time
                    print(peak_dbv)
                    # Trigger recording if signal exceeds threshold and not already recording *THIS IS THE CRITICAL PART WE NEED TO TEST IN DEPTH*
                    if peak_dbv > THRESHOLD_DBV and not recording_active[name]:
                        
                        # Check for new threshold crossing
                        swim_ins[name] += 1
                        last_crossed[name] = True
                        recording_active[name] = True              # Set recording active
                        
                        # Inside your main loop, start continuous recording
                        if continuous_recording_process is None:
                            output_filename = "/Users/omarebied/Desktop/E90/SwimForce/recorded_clips/continuous_recording.mp4"
                            continuous_recording_process = rec_clip_continuous(output_filename)

                        # When beep is detected
                        if peak_dbv > THRESHOLD_DBV and not recording_active[name]:
                            # Stop the continuous recording
                            continuous_recording_process.terminate()
                            continuous_recording_process.wait()  # Wait for the process to finish

                            # Increment the recording counter for the person
                            recording_counters[name] += 1
                            recording_number = recording_counters[name]

                            # Create a unique clip filename
                            clip_filename = f"/Users/omarebied/Desktop/E90/SwimForce/recorded_clips/{name}{recording_number}_clip.mp4"

                            # Create a clip from the last 5 seconds and the next 5 seconds
                            clip_command = [
                                "ffmpeg",
                                "-i", output_filename,
                                "-ss", "55",  # Start 5 seconds before the beep (assuming beep was detected at 60 seconds)
                                "-t", "10",   # Clip duration of 10 seconds (5 seconds before and 5 seconds after)
                                "-c:v", "libx264",
                                "-preset", "ultrafast",
                                "-crf", "23",
                                "-pix_fmt", "yuv420p",
                                clip_filename
                            ]

                            print("Creating clip...")
                            subprocess.run(clip_command)
                            print(f"Clip saved as: {clip_filename}")

                            # Restart continuous recording
                            continuous_recording_process = rec_clip_continuous(output_filename)

                        time.sleep(PULSE_DURATION)                 # Prevents overlap during recording
                        recording_active[name] = False             # Reset recording active
                    else:
                        last_crossed[name] = False

    close_device(hdwf)
    print("Data acquisition complete.")
else:
    print("Failed to open the device.")
