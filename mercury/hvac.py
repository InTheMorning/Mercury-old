import json
import logging
import paho.mqtt.client as mqtt
from logging import (debug, info, error, warning)
from serialcom import (setup_serial, read_serial, write_serial)


class HvacState:
    def __init__(self):
        self.serial = None
        self.status = 'Offline'
        self.hvac_code = 0
        self.action = 0
        self._aux = 0
        self._mode = 0
        self._toggle = 0

    @property
    def aux(self):
        if self.hvac_code == 3:
            return 1
        elif self.hvac_code == 2:
            return 0
        else:
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
            aux = self.aux * self.toggle
        else:
            aux = 0
        hvac_code = (value * self.toggle) + aux
        self.hvac_code = hvac_code
        self.set_action()
        self._mode = value

    @property
    def toggle(self):
        if self.hvac_code == 3:
            self.aux = 1
            return 1
        else:
            return self._toggle

    @toggle.setter
    def toggle(self, value):
        if self.mode == 2:
            aux = self.aux
        else:
            aux = 0
        hvac_code = value * (self.mode + aux)
        self.hvac_code = hvac_code
        self.set_action()
        self._toggle = value

    def change_hvac_state(self, hvac_code):
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

        if message.topic == ('hvac/call/toggle'):
            toggle = bool_string(message_string)
            info("Toggle message detected: %d", toggle)
            self.toggle = toggle
        elif message.topic == ('hvac/call/aux'):
            aux = bool_string(message_string)
            info("Aux message detected: %d", aux)
            self.aux = aux
        elif message.topic == ('hvac/call/mode'):
            mode = mode_string(message_string)
            info("Mode message detected: %d", mode)
            self.mode = mode

    def set_hvac_code(self, value):
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
            self.toggle = 1
        elif value == 0:
            self.toggle = 0

    def set_action(self):
        if self.mode == 2:
            if self.toggle == 1:
                self.action = action_string('heating')
            elif self.toggle == 0:
                self.action = action_string('idle')
        elif self.mode == 1:
            self.action = action_string('fan')
        if self.mode == 0:
            self.action = action_string('off')


def bool_string(input):
    _bool_strings = ['OFF', 'ON']
    if isinstance(input, int):
        return _bool_strings[input]
    elif isinstance(input, str):
        if input in _bool_strings:
            return _bool_strings.index(input)
        else:
            error("unrecognized boolean string %s", input)
    else:
        error("must be boolean or string, not %s", type(input))


def mode_string(input):
    _mode_strings = ['off', 'fan_only', 'heat']
    if isinstance(input, int):
        return _mode_strings[input]
    elif input in _mode_strings:
        return _mode_strings.index(input)
    else:
        error("Can not convert input %s", input)


def action_string(input):
    _action_strings = ['off', 'fan', 'idle', 'heating']
    if isinstance(input, int):
        return _action_strings[input]
    elif input in _action_strings:
        return _action_strings.index(input)
    else:
        error("Can not convert input %s", input)


def loop(client, hvac_state):

    hvac_state.fetch_hvac_state()
    action = hvac_state.action
    aux = hvac_state.aux
    mode = hvac_state.mode
    toggle = hvac_state.toggle
    hvac_code = hvac_state.hvac_code
    status = hvac_state.status

    while True:
        client.loop(3)
        if aux != hvac_state.aux:
            aux = hvac_state.aux
            info("Publishing aux: %s", aux)
            client.publish('hvac/state/aux', bool_string(aux))
        elif mode != hvac_state.mode:
            mode = hvac_state.mode
            info("Publishing mode: %s", mode)
            client.publish('hvac/state/mode', mode_string(mode))
        elif toggle != hvac_state.toggle:
            toggle = hvac_state.toggle
            info("Publishing switch state: %s", toggle)
            client.publish('hvac/state/toggle', bool_string(toggle))
        elif action != hvac_state.action:
            action = hvac_state.action
            info("Publishing action: %s", action)
            client.publish('hvac/state/action', action_string(action))
        elif hvac_code != hvac_state.hvac_code:
            hvac_code = hvac_state.hvac_code
            info("Sending new state to hvac: %s", hvac_code)
            hvac_state.change_hvac_state(hvac_code)
        else:
            hvac_state.fetch_hvac_state()
            if status != hvac_state.status:
                status = hvac_state.status
                info("Publishing status: %s", status)
                client.publish('hvac/state/status',
                               json.dumps({'status': status}))


def main(port, broker_address):
    hvac_state = HvacState()
    client = mqtt.Client("HVAC")  # create new instance

    # Start serial connection
    hvac_state.serial = setup_serial(port, 9600, 1)

    info("creating new instance")
    client.on_message = hvac_state.on_mqtt_message  # attach function to callback

    info("connecting to broker %s", broker_address)
    client.connect(broker_address)  # connect to broker

    info("Subscribing to topics")
    client.subscribe("hvac/call/aux")
    client.subscribe("hvac/call/mode")
    client.subscribe("hvac/call/toggle")

    loop(client, hvac_state)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main('/dev/ttyAMA0', 'localhost')
