"""Fixed offline responder for the isolation and deadline probe."""
import signal
import sys
import time

signal.alarm(30)
data = sys.stdin.buffer.read(32_770)
if data[:1] == b'1':
    sys.stdout.buffer.write(data[1:2])
    sys.stdout.buffer.flush()
    time.sleep(60)
else:
    sys.stdout.buffer.write(data[1:])
