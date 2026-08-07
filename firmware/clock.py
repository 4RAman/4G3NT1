# One monotonic, wrap-safe clock for the whole firmware.
#
# MicroPython's ticks_ms() wraps (2**30 ms, about 12.4 days) and must be
# compared with ticks_diff(), never subtracted. Rather than teach every
# caller that, now_s() accumulates the diffs into a float of seconds that
# only ever increases - which is exactly what trigger.py's timestamps and
# the animation phases assume. As long as something calls it more often
# than every few days (the poll loop calls it every 10 ms) it cannot wrap.
#
# The CPython fallback is what lets led.py, buzzer.py and trigger.py be
# imported by the test suite on the host.

try:  # MicroPython
    from time import ticks_diff, ticks_ms
except ImportError:  # CPython, for tests on the host
    from time import monotonic

    def ticks_ms():
        return int(monotonic() * 1000)

    def ticks_diff(new, old):
        return new - old


_last = ticks_ms()
_elapsed_ms = 0


def now_s():
    """Seconds since boot, monotonic and wrap-safe."""
    global _last, _elapsed_ms
    t = ticks_ms()
    _elapsed_ms += ticks_diff(t, _last)
    _last = t
    return _elapsed_ms / 1000
