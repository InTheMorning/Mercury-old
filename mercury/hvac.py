import json
import logging
from enum import Enum
from logging import debug, error, info, warning

import paho.mqtt.client as mqtt

from utils import read_serial, setup_serial, write_serial


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
        self.hvac_code = 0
        self._aux = 0
        self._mode = 0
        self._toggle = 0

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
            else:
                warning("invalid mode number received: %s", hvac_code)
                return
            self.status = status
        else:
            warning("no json to parse")
            return

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


def loop(client, hvac_state):
    debug("starting main loop")
    hvac_state.fetch_hvac_state()

    action = hvac_state.action
    aux = hvac_state.aux
    hvac_code = hvac_state.hvac_code
    mode = hvac_state.mode
    toggle = hvac_state.toggle
    status = hvac_state.status
    debug("action: %s, aux: %s, hc: %d, mode: %s, toggle: %s",
          ActionValue(action).name,
          BoolValue(aux).name,
          hvac_code,
          ModeValue(mode).name,
          BoolValue(toggle).name
          )
    while True:
        debug("running mqtt loop")
        client.loop(5)
        debug("action: %s, aux: %s, hc: %d, mode: %s, toggle: %s",
              ActionValue(action).name,
              BoolValue(aux).name,
              hvac_code,
              ModeValue(mode).name,
              BoolValue(toggle).name
              )
        if aux != hvac_state.aux:
            aux = hvac_state.aux
            info("Publishing aux: %s", BoolValue(aux).name)
            client.publish('hvac/state/aux', BoolValue(aux).name)
        if hvac_code == hvac_state.hvac_code:
            if mode != hvac_state.mode:
                mode = hvac_state.mode
                info("Publishing mode: %s", ModeValue(mode).name)
                client.publish('hvac/state/mode', ModeValue(mode).name)
            if toggle != hvac_state.toggle:
                toggle = hvac_state.toggle
                info("Publishing switch state: %s", BoolValue(toggle).name)
                client.publish('hvac/state/toggle', BoolValue(toggle).name)
            if action != hvac_state.action:
                action = hvac_state.action
                info("Publishing action: %s", ActionValue(action).name)
                client.publish('hvac/state/action', ActionValue(action).name)
            hvac_state.fetch_hvac_state()

        else:
            hc = hvac_state.hvac_code
            info("Sending new state to hvac: %s", hc)
            hvac_state.change_hvac_state(hc)
            hvac_state.fetch_hvac_state()
            hvac_code = hvac_state.hvac_code

        if status != hvac_state.status:
            status = hvac_state.status
            info("Publishing status: %s", status)
            client.publish('hvac/state/status',
                           json.dumps({'status': status}))


def main(port, broker_address):
    hvac_state = HvacState()
    client = mqtt.Client("HVAC")

    hvac_state.serial = setup_serial(port, 9600, 1)

    info("creating new instance")
    client.on_message = hvac_state.on_mqtt_message

    info("connecting to broker %s", broker_address)
    client.connect(broker_address)

    info("Subscribing to topics")
    client.subscribe("hvac/call/aux")
    client.subscribe("hvac/call/mode")
    client.subscribe("hvac/call/toggle")
    loop(client, hvac_state)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main('/dev/ttyAMA0', 'localhost')
