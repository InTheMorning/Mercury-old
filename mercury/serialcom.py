import atexit
import serial
import json
from logging import (debug, info, warning, error)
from time import sleep


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
            debug("empty response from serial")
            return


def write_serial(ser, i):
    s = str(i) + '\n'
    ser.write(s.encode(encoding='UTF-8'))
    sleep(0.011)
    return
