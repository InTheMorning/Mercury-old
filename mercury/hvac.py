import json
import logging
from datetime import datetime, timedelta
from enum import Enum
from logging import debug, error, info, warning

import paho.mqtt.client as mqtt

from utils import (choose_state_file, load_state, read_serial, save_state,
                   setup_serial, write_serial)


class ActionValue(Enum):
    off = 0
    fan = 1
    idle = 2
    heating = 3


class BoolValue(Enum):
    OFF = 0
    ON = 1


class ModeValue(Enum):
    off = 0
    fan_only = 1
    heat = 2


class Topics():
    def __init__(self) -> None:
        self.call_prefix = 'hvac/call/'
        self.state_prefix = 'hvac/state/'
        self.calls = {}
        self.states = {}
        for t in ['aux', 'mode', 'toggle']:
            self.calls[t] = self.call_prefix + t
        for t in ['aux', 'mode', 'toggle', 'action', 'status']:
            self.states[t] = self.state_prefix + t

    def call(self, string):
        if string in self.calls.values():
            for key, value in self.calls.items():
                if string == value:
                    return key
        elif string in self.calls.keys():
            return self.calls[string]

    def state(self, string):
        if string in self.states.values():
            for key, value in self.states.items():
                if string == value:
                    return key
        elif string in self.states.keys():
            return self.states[string]


class HvacState:
    def __init__(self) -> None:
        self._aux = None
        self._mode = None
        self._toggle = None
        self.client = None
        self.hvac_code = None
        self.serial = None
        self.status = 'Offline'

    @property
    def action(self):
        if self.mode == 2:
            if self.toggle == 1:
                return ActionValue.heating.value
            elif self.toggle == 0:
                return ActionValue.idle.value
        elif self.mode == 1:
            return ActionValue.fan.value
        elif self.mode == 0:
            return ActionValue.off.value

    @property
    def aux(self):
        return self._aux

    @aux.setter
    def aux(self, value):
        if value == 1:
            if self.hvac_code == 2:
                self.hvac_code = 3
        elif value == 0:
            if self.hvac_code == 3:
                self.hvac_code = 2
        self._aux = value

    @property
    def mode(self):
        return self._mode

    @mode.setter
    def mode(self, value):
        if value == 2:
            hvac_code = value * self.toggle + (self.toggle * self.aux)
        else:
            hvac_code = value
        self.hvac_code = hvac_code
        self._mode = value

    @property
    def toggle(self):
        return self._toggle

    @toggle.setter
    def toggle(self, value):
        if self.mode == 2:
            self.hvac_code = value * (self.mode + self.aux)
            self._toggle = value
        else:
            self._toggle = 0

    def change_hvac_state(self, hvac_code):
        debug("sending %d state to hvac", hvac_code)
        ser = self.serial
        valid = False
        tries = 0
        response = ''
        while not valid and tries < 60:
            write_serial(ser, hvac_code)
            response = read_serial(ser)
            tries += 1
            if isinstance(response, int):
                valid = True
        debug("tried %d times", tries)
        if response == hvac_code:
            debug("received mode number %d confirmation", hvac_code)
        else:
            error("got wrong confirmation from hvac:"
                  "expected %s, got %s" % (hvac_code, response))

    def fetch_hvac_state(self):
        debug("fetching state from hvac")
        ser = self.serial
        write_serial(ser, 10)
        json_obj = read_serial(ser)

        if json_obj:
            hvac_code = json_obj['mode']
            status = json_obj['status']
            if hvac_code in range(0, 4):
                self.set_hvac_code(hvac_code)
                self.status = status
            else:
                warning("hvac invalid mode number: %s", hvac_code)
        else:
            warning("no json to parse")
        return datetime.now()

    def on_mqtt_message(self, client, userdata, message):
        payload = str(message.payload.decode("utf-8"))

        debug("message received %s", payload)
        debug("message topic=%s", message.topic)
        debug("message qos=%d", message.qos)
        debug("message retain flag=%d", message.retain)

        if message.topic in Topics().calls.values():
            topic = Topics().call(message.topic)
            data = mqtt_decode(topic, payload)
            info("%s message detected: %s", topic, data)

            if topic == 'aux':
                if data != self.aux:
                    self.aux = data
                else:
                    info("%s already set, republishing", topic)
                    self.publish(topic, data)

            elif topic == 'mode':
                if data != self.mode:
                    self.mode = data
                else:
                    info("%s already set, republishing", topic)
                    self.publish(topic, data)

            elif topic == 'toggle':
                if data != self.toggle:
                    self.toggle = data
                else:
                    info("%s already set, republishing", topic)
                    self.publish(topic, data)

    def publish(self, topic, data):
        payload = mqtt_encode(topic, data)
        info("Publishing %s: %s", topic, payload)
        self.client.publish(Topics().state(topic),
                            payload,
                            retain=True)

    def set_hvac_code(self, value):
        debug("setting values according to hvac code %d", value)
        if value == 3:
            self.aux = 1
            self.mode = 2
            self.toggle = 1
        elif value == 2:
            self.aux = 0
            self.mode = 2
            self.toggle = 1
        elif value == 1:
            self.mode = 1
            self.toggle = 0
        elif value == 0:
            self.toggle = 0
            self.hvac_code = value


def mqtt_decode(topic, string):
    if topic in ['aux', 'toggle']:
        return BoolValue[string].value
    elif topic == 'mode':
        return ModeValue[string].value
    elif topic == 'action':
        return ActionValue[string].value
    else:
        return string


def mqtt_encode(topic, data):
    if topic in ['aux', 'toggle']:
        return BoolValue(data).name
    elif topic == 'mode':
        return ModeValue(data).name
    elif topic == 'action':
        return ActionValue(data).name
    elif topic == 'status':
        return json.dumps({'status': data})


def loop(hvac_state, statefile):
    info("Subscribing to topics")
    for val in Topics().calls.values():
        hvac_state.client.subscribe(val)

    info("Preparing main loop")
    previous_state = load_state(statefile)
    hvac_state.aux = previous_state['aux']
    hvac_state.toggle = previous_state['toggle']
    hvac_state.mode = previous_state['mode']
    last_fetch_time = hvac_state.fetch_hvac_state()
    previous_state = {'aux': hvac_state.aux,
                      'action': hvac_state.action,
                      'hvac_code': hvac_state.hvac_code,
                      'mode': hvac_state.mode,
                      'status': hvac_state.status,
                      'toggle': hvac_state.toggle,
                      }
    debug(previous_state)
    hvac_state.publish('aux', previous_state['aux'])
    hvac_state.publish('mode', previous_state['mode'])
    hvac_state.publish('toggle', previous_state['toggle'])
    hvac_state.publish('action', previous_state['action'])
    hvac_state.publish('status', previous_state['status'])

    info("Starting main loop")
    while True:
        debug("running mqtt loop")
        hvac_state.client.loop(1)

        # Publish changes
        if previous_state['hvac_code'] == hvac_state.hvac_code:
            if previous_state['aux'] != hvac_state.aux:
                aux = hvac_state.aux
                hvac_state.publish('aux', aux)
                previous_state['aux'] = aux
            if previous_state['mode'] != hvac_state.mode:
                mode = hvac_state.mode
                hvac_state.publish('mode', mode)
                previous_state['mode'] = mode
            if previous_state['toggle'] != hvac_state.toggle:
                toggle = hvac_state.toggle
                hvac_state.publish('toggle', toggle)
                previous_state['toggle'] = toggle
            if previous_state['action'] != hvac_state.action:
                action = hvac_state.action
                hvac_state.publish('action', action)
                previous_state['action'] = action
            if previous_state['status'] != hvac_state.status:
                status = hvac_state.status
                hvac_state.publish('status', status)
                previous_state['status'] = status
            # refresh if needed
            if datetime.now() - last_fetch_time >= timedelta(seconds=2):
                last_fetch_time = hvac_state.fetch_hvac_state()

        else:
            # send new state to hvac
            hc = hvac_state.hvac_code
            info("Sending new state to hvac: %s", hc)
            hvac_state.change_hvac_state(hc)
            last_fetch_time = hvac_state.fetch_hvac_state()
            previous_state['hvac_code'] = hvac_state.hvac_code
            save_state(statefile, previous_state)


def main(port, broker_address):
    hvac_state = HvacState()

    info("Connecting to mqtt broker %s", broker_address)
    hvac_state.client = mqtt.Client("HVAC")
    hvac_state.client.connect(broker_address)
    hvac_state.client.on_message = hvac_state.on_mqtt_message

    info("Setting up serial device")
    hvac_state.serial = setup_serial(port, 9600, 1)

    statefile = choose_state_file()

    loop(hvac_state, statefile)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main('/dev/ttyAMA0', 'localhost')
