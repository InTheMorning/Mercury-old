import atexit
import json
from logging import debug, error, info, warning
from os import chmod, mknod, path, remove, stat
from time import sleep

import serial


def choose_state_file():
    filename = path.join('/tmp', 'hvac.state.json')
    debug("Setting state file to %s", filename)
    if path.isfile(filename):
        if oct(stat(filename).st_mode)[-3:] == '600':
            return filename
        else:
            remove(filename)
    mknod(filename)
    chmod(filename, 0o600)


def load_state(filename):
    defaults = {'action': 0,
                'aux': 0,
                'hvac_code': 0,
                'mode': 0,
                'toggle': 0,
                'status': 'Offline'
                }
    debug("Loading state from %s...", filename)
    try:
        with open(filename, 'r') as f:
            state = json.load(f)
    except BaseException as e:
        debug(e)
        warning("valid state file not found, using defaults")
        state = defaults
    return state


def save_state(filename, state):
    debug("Saving to file %s :  %s", filename, state)
    with open(filename, 'w') as f:
        json.dump(state, f)


def setup_serial(device, baudrate, timeout):
    debug("Getting heater serial connection...")
    try:
        ser = serial.Serial(device, baudrate, timeout=timeout)
        info("Heater connected via serial connection.")
    except BaseException:
        error("Failed to start serial connection.  The program will exit.")
        raise
    else:
        atexit.register(ser.close)
        return ser


def read_serial(ser):
    try:
        response = ser.readline().decode(encoding='UTF-8').strip()
    except BaseException as e:
        error("serial error: %s", e)
        return
    else:
        if response:
            if response.isdigit():
                debug("serial returning int %s", response)
                return int(response)
            else:
                debug("received string response: %s", response)
                try:
                    json_obj = json.loads(response)
                    debug("received valid json: %s", json_obj)
                    return json_obj
                except BaseException as e:
                    warning("received invalid json: %s", e)
        else:
            warning("empty response from serial")
            return


def write_serial(ser, i):
    s = str(i) + '\n'
    ser.write(s.encode(encoding='UTF-8'))
    sleep(0.011)
    return
