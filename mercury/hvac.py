import atexit
import json
from logging import (debug, info, error, critical, warning)
import logging
import paho.mqtt.client as mqtt
import serial
from time import sleep


class HvacState:
    def __init__(self):
        self.aux = 'OFF'
        self.mode_number = 0
        self.mode = 'off'
        self.serial = None
        self.status = 'Offline'
        self.temporary_statuses = {
                "Pre-heating",
                "Warming up",
                "Cooling down"
                }

    def fetch_hvac_mode(self):
        ser = self.serial
        valid = False

        # get mode number
        while not valid:
            write_serial(ser, 11)
            response = read_serial(ser, 'int')
            if isinstance(response, int):
                valid = True

        mode_number = response

        if mode_number in range(2, 4):
            mode = 'heat'
        elif mode_number == 1:
            mode = 'fan_only'
        elif mode_number == 0:
            mode = 'off'
        else:
            error("invalid mode number received: %s", mode_number)
            return

        self.mode_number = mode_number
        self.mode = mode
        self.fetch_hvac_status()

    def fetch_hvac_status(self):
        ser = self.serial
        valid = False
        tries = 0
        while not valid and tries < 60:
            if self.status not in self.temporary_statuses and tries < 10:
                write_serial(ser, 10)
            response = read_serial(ser, 'str')
            if isinstance(response, str):
                if len(response) in range(3, 21):
                    self.status = response
                    valid = True
            tries += 1

    def change_hvac_state(self, mode_number):
        ser = self.serial
        valid = False
        tries = 0
        while not valid and tries < 60:
            write_serial(ser, mode_number)
            response = read_serial(ser, 'int')
            if isinstance(response, int):
                valid = True
        if response == mode_number:
            debug("received mode number %d confirmation", mode_number)
            self.fetch_hvac_mode()
        else:
            error("got wrong confirmation from hvac:"
                "expected %s, got %s" % (mode_number, response))

    def setup_serial(self, device='/dev/ttyAMA0', baudrate=9600, timeout=1):
        debug("Getting heater serial connection...")
        try:
            ser = serial.Serial(device, baudrate, timeout=timeout)
            info("Heater connected via serial connection.")
        except BaseException:
            error("Failed to start serial connection.  The program will exit.")
            raise
        else:
            atexit.register(ser.close)
            self.serial = ser


def read_serial(ser, x):
    try:
        response = ser.readline().decode(encoding='UTF-8').strip()
    except BaseException as e:
        error("serial error: %s", e)
        return
    else:
        if response:
            if x == 'int':
                if response.isdigit():
                    debug("serial returning int %s", response)
                    return int(response)
                else:
                    error("invalid response, %s is not an int", response)
                    return
            elif x == 'str':
                debug("received string response: %s", response)
                return response
        else:
            debug("serial empty response")
            return


def write_serial(ser, i):
    s = str(i) + '\n'
    ser.write(s.encode(encoding='UTF-8'))
    sleep(0.011)
    return


def on_message(client, userdata, message):
    message_string = str(message.payload.decode("utf-8"))
    debug("message received %s", message_string)
    debug("message topic=%s", message.topic)
    debug("message qos=%d", message.qos)
    debug("message retain flag=%d", message.retain)
    if message.topic == ('hvac/call/aux'):
        aux = message_string
        if aux == 'ON':
            if h.mode_number == 2:
                h.change_hvac_state(3)
        elif aux == 'OFF':
            if h.mode_number == 3:
                h.change_hvac_state(2)
        else:
            error('invalid aux state: %s', aux)
            return
        h.aux = aux
        client.publish("hvac/state/aux", aux)

    elif message.topic == ('hvac/call/mode'):
        mode = message_string
        if mode == 'heat':
            if h.aux == 'ON':
                mode_number = 3
            else:
                mode_number = 2
        elif mode == 'fan_only':
            mode_number = 1
        elif mode == 'off':
            mode_number = 0
        else:
            error("invalid mode: %s", mode)
            return
        h.change_hvac_state(mode_number)
        h.mode = mode
        client.publish("hvac/state/mode", mode)


logging.basicConfig(level=logging.DEBUG)

# Start serial connection
h = HvacState()
h.setup_serial()
h.fetch_hvac_mode()

broker_address = "localhost"
info("creating new instance")
client = mqtt.Client("HVAC")  # create new instance
client.on_message = on_message  # attach function to callback

info("connecting to broker %s", broker_address)
client.connect(broker_address)  # connect to broker
client.loop_start()  # start the loop

info("Subscribing to topics")
client.subscribe("hvac/call/mode")
client.subscribe("hvac/call/aux")

info("Publishing message to topic")
client.publish("hvac/state/aux", h.aux)
client.publish("hvac/state/mode", h.mode)


while True:
    h.fetch_hvac_status()
    cached_status = h.status
    info("got current status: %s", cached_status)
    state_json = json.dumps({'status': cached_status})
    client.publish("hvac/state/status", state_json)
    while True:
        if h.status != cached_status:
            break
        sleep(0.5)

client.loop_stop()
