# Experiment only: make every fsync slow, as on a cold disk, to widen the envelope->profile write window.
import os, time
_fsync = os.fsync
def _slow(fd):
    time.sleep(float(os.environ.get("SLOW_FSYNC", "0.03")))
    return _fsync(fd)
os.fsync = _slow
