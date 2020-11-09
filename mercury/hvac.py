import atexit
from logging import (debug, info, error, critical, warning)
import logging
import paho.mqtt.client as mqtt
import serial
import time


class HvacState:
    def __init__(self):
        self.aux = 'OFF'
        self.mode_number = 0
        self.mode = 'off'
        self.serial = None
        self.status = 'offline'

    def fetch_hvac_state(self):
        ser = self.serial

        # get status string
        ser.write(b'10\n')
        response = ser.readline().decode(encoding='UTF-8').strip()
        status = response

        # get mode number
        ser.write(b'11\n')
        response = ser.readline().decode(encoding='UTF-8').strip()
        mode_number = int(response)

        if mode_number == 3:
            mode = 'heat'
            aux = 'ON'
        elif mode_number == 2:
            aux = 'OFF'
            mode = 'heat'
        elif mode_number == 1:
            mode = 'fan_only'
            aux = None
        elif mode_number == 0:
            mode = 'off'
            aux = None
        else:
            error("invalid mode number recieved")
            return

        if aux == 'ON' or aux == 'OFF':
            self.aux = aux
        self.mode_number = mode_number
        self.mode = mode
        if len(status) in range(3, 21):
            self.status = status

    def change_hvac_state(self, mode_number):
        ser = self.serial
        message = str(mode_number) + '\n'
        ser.write(message.encode(encoding='UTF-8'))
        response = ser.readline().decode(encoding='UTF-8').strip()
        if int(response) == mode_number:
            self.fetch_hvac_state()
        else:
            error('Did not receive confirmation packet')

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


def on_message(client, userdata, message):
    message_string = str(message.payload.decode("utf-8"))
    debug("message received %s", message_string)
    debug("message topic=%s", message.topic)
    debug("message qos=%d", message.qos)
    debug("message retain flag=%d", message.retain)
    client.publish("hvac/state/aux", h.aux)
    client.publish("hvac/state/mode", h.mode)
    client.publish("hvac/state/status", h.status)


logging.basicConfig(level=logging.DEBUG)

# Start serial connection
h = HvacState()
h.setup_serial()
h.fetch_hvac_state()

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
client.publish("hvac/state/mode", "heat")
client.publish("hvac/state/aux", "ON")
time.sleep(40)
client.publish("hvac/state/mode", "off")
client.publish("hvac/state/aux", "OFF")
client.loop_stop()
