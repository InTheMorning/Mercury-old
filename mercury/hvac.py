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


class HvacState:
    def __init__(self):
        self.serial = None
        self.status = 'Offline'
        self.hvac_code = None
        self._aux = None
        self._mode = None
        self._toggle = None

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
        message_string = str(message.payload.decode("utf-8"))
        debug("message received %s", message_string)
        debug("message topic=%s", message.topic)
        debug("message qos=%d", message.qos)
        debug("message retain flag=%d", message.retain)

        if message.topic == ('hvac/call/aux'):
            info("Aux message detected: %s", message_string)
            self.aux = BoolValue[message_string].value
        elif message.topic == ('hvac/call/mode'):
            info("Mode message detected: %s", message_string)
            self.mode = ModeValue[message_string].value
        elif message.topic == ('hvac/call/toggle'):
            info("Toggle message detected: %s", message_string)
            self.toggle = BoolValue[message_string].value

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


def loop(client, hvac_state, statefile):
    info("Preparing main loop")
    previous_state = load_state(statefile)
    hvac_state.aux = previous_state['aux']
    hvac_state.toggle = previous_state['toggle']
    hvac_state.mode = previous_state['mode']
    last_fetch_time = hvac_state.fetch_hvac_state()
    client.loop(0)
    previous_state = {'aux': hvac_state.aux,
                      'action': hvac_state.action,
                      'hvac_code': hvac_state.hvac_code,
                      'mode': hvac_state.mode,
                      'status': hvac_state.status,
                      'toggle': hvac_state.toggle,
                      }
    client.publish('hvac/state/aux',
                   BoolValue(previous_state['aux']).name)
    client.publish('hvac/state/mode',
                   ModeValue(previous_state['mode']).name)
    client.publish('hvac/state/toggle',
                   BoolValue(previous_state['toggle']).name)
    client.publish('hvac/state/action',
                   ActionValue(previous_state['action']).name)
    client.publish('hvac/state/status',
                   json.dumps({'status': previous_state['status']}))

    info("Starting main loop")
    while True:
        debug("action: %s, aux: %s, hc: %d, mode: %s, toggle: %s",
              ActionValue(previous_state['action']).name,
              BoolValue(previous_state['aux']).name,
              previous_state['hvac_code'],
              ModeValue(previous_state['mode']).name,
              BoolValue(previous_state['toggle']).name
              )
        debug("running mqtt loop")
        client.loop(5)

        if previous_state['hvac_code'] == hvac_state.hvac_code:
            if previous_state['aux'] != hvac_state.aux:
                aux = hvac_state.aux
                info("Publishing aux: %s", BoolValue(aux).name)
                client.publish('hvac/state/aux', BoolValue(aux).name)
                previous_state['aux'] = aux
            if previous_state['mode'] != hvac_state.mode:
                mode = hvac_state.mode
                info("Publishing mode: %s", ModeValue(mode).name)
                client.publish('hvac/state/mode', ModeValue(mode).name)
                previous_state['mode'] = mode
            if previous_state['toggle'] != hvac_state.toggle:
                toggle = hvac_state.toggle
                info("Publishing switch state: %s", BoolValue(toggle).name)
                client.publish('hvac/state/toggle', BoolValue(toggle).name)
                previous_state['toggle'] = toggle
            if previous_state['action'] != hvac_state.action:
                action = hvac_state.action
                info("Publishing action: %s", ActionValue(action).name)
                client.publish('hvac/state/action', ActionValue(action).name)
                previous_state['action'] = action
            if previous_state['status'] != hvac_state.status:
                status = hvac_state.status
                info("Publishing status: %s", status)
                client.publish('hvac/state/status',
                               json.dumps({'status': status}))
                previous_state['status'] = status
            if datetime.now() - last_fetch_time >= timedelta(seconds=2):
                last_fetch_time = hvac_state.fetch_hvac_state()

        else:
            hc = hvac_state.hvac_code
            info("Sending new state to hvac: %s", hc)
            hvac_state.change_hvac_state(hc)
            last_fetch_time = hvac_state.fetch_hvac_state()
            previous_state['hvac_code'] = hvac_state.hvac_code
            save_state(statefile, previous_state)


def main(port, broker_address):
    hvac_state = HvacState()
    client = mqtt.Client("HVAC")

    info("Setting up serial device")
    hvac_state.serial = setup_serial(port, 9600, 1)

    client.on_message = hvac_state.on_mqtt_message

    info("Connecting to mqtt broker %s", broker_address)
    client.connect(broker_address)

    info("Subscribing to topics")
    client.subscribe("hvac/call/aux")
    client.subscribe("hvac/call/mode")
    client.subscribe("hvac/call/toggle")

    statefile = choose_state_file()

    loop(client, hvac_state, statefile)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main('/dev/ttyAMA0', 'localhost')
