import time
import serial

PORT = "/dev/ttyACM0"
BAUD = 9600

try:
    ser = serial.Serial(PORT, BAUD, timeout=1)
    print(f"Connected to {PORT}. Waiting 2 seconds for Arduino DTR reset...")
    time.sleep(2)
except Exception as e:
    print(f"Failed to connect to {PORT}: {e}")
    exit(1)

# Sequence test: cycle through lanes or send commands
print("Testing commands...")
for lane in range(1, 5):
    # Test format A (SET format)
    cmd_set = f"SET:{lane}:4\n"
    print(f"Sending: {cmd_set.strip()}")
    ser.write(cmd_set.encode("utf-8"))
    
    # Check if Arduino sends any feedback back
    time.sleep(0.5)
    while ser.in_waiting:
        print("Arduino reply:", ser.readline().decode().strip())
    
    time.sleep(3)

ser.close()
print("Done. Did the LEDs switch?")