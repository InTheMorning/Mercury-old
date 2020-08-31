import atexit
import logging
import serial

from functools import wraps
from logging import error, info, debug
from threading import current_thread as get_current_thread


def try_function(on_failure, method, *args, **kwargs):
    '''Attempt to run method, passing arguments *args and **kwargs. If it
    fails, defer to on_failure callback

    '''

    try:
        method(*args, **kwargs)
    except Exception:
        logging.exception("Failed to run function %s.%s"
                          % (method.__module__, method.__name__))
        on_failure()


def setup_logging(**kwargs):
    '''Setup logging so that it includes timestamps.'''

    kwargs.setdefault('force', True)
    kwargs.setdefault('level', logging.INFO)
    kwargs.setdefault('format', '%(levelname)-8s %(message)s')
    kwargs.setdefault('datefmt', '%Y-%m-%d %H:%M:%S')

    logging.basicConfig(**kwargs)


def setup_serial(device='/dev/AMA0', baudrate=9600:
    debug("Getting heater serial connection...")

    try:
        ser = serial.Serial(device, baudrate, timeout=1)
        info("Heater connected via serial connection.")

    except BaseException:
        error("Failed to start serial connection.  The program will exit.")
        raise

    else:
        atexit.register(ser.close)
        return ser


def logged_thread_start(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        thread = get_current_thread()
        info("Started thread %s [%s]."
             % (thread.name, thread.native_id))
        return func(*args, **kwargs)

    return wrapper
