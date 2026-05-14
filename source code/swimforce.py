import numpy as np
import time
import ctypes
import matplotlib.pyplot as plt
from scipy.signal import butter, lfilter

# === Load WaveForms SDK ===
dwf = ctypes.CDLL("/Library/Frameworks/dwf.framework/dwf")

# === Parameters ===
SAMPLE_RATE = 250_000  # 200 kHz
BUFFER_SIZE = 16384    # Match WaveForms settings
PULSE_DURATION = 10     # Monitor for 10 seconds
ORDER = 4  # Order of the bandpass filter
LOG_INTERVAL = 0.01  # Log data every 0.01 seconds
THRESHOLD_DBV = -70  # Threshold for logging timestamps

# Frequency ranges per person
PEOPLE = {
    # "cami": (19000, 21000),
    # "omar": (20100, 20300),
    "cole": (99000, 101000),
    # "ham": (49000, 51000),
}

# Track threshold crossings
swim_ins = {name: 0 for name in PEOPLE}
last_crossed = {name: False for name in PEOPLE}

# === Initialize AD2 ===
def open_device():
    hdwf = ctypes.c_int()
    dwf.FDwfDeviceOpen(ctypes.c_int(-1), ctypes.byref(hdwf))
    if hdwf.value == 0:
        print("Failed to open AD2 device.")
        return None
    return hdwf

def close_device(hdwf):
    dwf.FDwfDeviceClose(hdwf)

# === Configure AD2 analog input ===
def configure_device(hdwf):
    dwf.FDwfAnalogInChannelEnableSet(hdwf, ctypes.c_int(0), ctypes.c_int(1))  # Enable CH1
    dwf.FDwfAnalogInFrequencySet(hdwf, ctypes.c_double(SAMPLE_RATE))
    dwf.FDwfAnalogInBufferSizeSet(hdwf, ctypes.c_int(BUFFER_SIZE))
    dwf.FDwfAnalogInConfigure(hdwf, ctypes.c_bool(False), ctypes.c_bool(True))

# === Read data from AD2 ===
def read_data(hdwf):
    data = (ctypes.c_double * BUFFER_SIZE)()
    dwf.FDwfAnalogInStatus(hdwf, ctypes.c_bool(True), None)
    dwf.FDwfAnalogInStatusData(hdwf, ctypes.c_int(0), data, ctypes.c_int(BUFFER_SIZE))
    return np.array(data)

# === Bandpass Filter ===
def butter_bandpass(lowcut, highcut, fs, order=5):
    nyq = 0.5 * fs
    low = lowcut / nyq
    high = highcut / nyq
    b, a = butter(order, [low, high], btype='band')
    return b, a

def butter_bandpass_filter(data, lowcut, highcut, fs, order=5):
    b, a = butter_bandpass(lowcut, highcut, fs, order=order)
    y = lfilter(b, a, data)
    return y

# === Store data ===
timestamp_dbv_data = {name: [] for name in PEOPLE}
thresh_crossings = {name: [] for name in PEOPLE}

# === Main Loop ===
hdwf = open_device()

if hdwf:
    configure_device(hdwf)
    start_time = time.time()
    last_log_time = start_time
    collecting = True
    print("Starting data acquisition...")

    while time.time() - start_time < PULSE_DURATION:
        current_time = time.time()
        
        if collecting and current_time - last_log_time >= LOG_INTERVAL:
            last_log_time = current_time
            collecting = False  # Switch off for 1 interval
        elif not collecting and current_time - last_log_time >= LOG_INTERVAL:
            last_log_time = current_time
            collecting = True  # Switch back on
        
        if collecting:
            data = read_data(hdwf)

            for name, (low, high) in PEOPLE.items():
                filtered_data = butter_bandpass_filter(data, low, high, SAMPLE_RATE, order=ORDER)

                # Apply windowing and FFT
                window = np.blackman(len(filtered_data))
                windowed = filtered_data * window
                correction_factor = np.sum(window) / len(filtered_data)
                fft_result = np.fft.rfft(windowed) / (BUFFER_SIZE * correction_factor)
                magnitudes = 20 * np.log10(np.abs(fft_result) + 1e-12)

                freqs = np.fft.rfftfreq(len(filtered_data), 1 / SAMPLE_RATE)
                target_idx = np.where((freqs >= low) & (freqs <= high))[0]

                if len(target_idx) > 0:
                    peak_dbv = np.max(magnitudes[target_idx])
                    timestamp = current_time - start_time
                    timestamp_dbv_data[name].append((timestamp, peak_dbv))

                    if peak_dbv > THRESHOLD_DBV:
                        # Check for new threshold crossing
                        if not last_crossed[name]:
                            swim_ins[name] += 1
                            last_crossed[name] = True
                            print(f"{name} swam in at {timestamp:.2f} sec")
                            thresh_crossings[name].append(timestamp)
                    else:
                        last_crossed[name] = False

    close_device(hdwf)
    print("Data acquisition complete.")

    # Save data and plot
    for name in PEOPLE:
        if timestamp_dbv_data[name]:
            # Save extracted data
            with open(f"{name}_filtered_data.csv", "w") as f:
                f.write("Timestamp (s),Amplitude (dBV)\n")
                for timestamp, dbv in timestamp_dbv_data[name]:
                    f.write(f"{timestamp:.6f},{dbv:.6f}\n")

            # Save threshold crossings
            with open(f"{name}_threshold_crossings.csv", "w") as f:
                f.write("Timestamp (s)\n")
                for timestamp in thresh_crossings[name]:
                    f.write(f"{timestamp:.6f}\n")

            # Plot results
            timestamps, dbv_values = zip(*timestamp_dbv_data[name])
            plt.figure(figsize=(10, 5))
            plt.plot(timestamps, dbv_values, label=f'{name} Signal Amplitude', color='blue')
            plt.axhline(y=THRESHOLD_DBV, color='r', linestyle='--', label=f'Threshold ({THRESHOLD_DBV} dBV)')
            plt.xlabel("Time (s)")
            plt.ylabel("Peak Amplitude (dBV)")
            plt.title(f"{name} Signal Over Time")
            plt.legend()
            plt.grid()
            plt.show()

        else:
            print(f"No valid data collected for {name} within the specified frequency range.")
else:
    print("Failed to open the device.")
