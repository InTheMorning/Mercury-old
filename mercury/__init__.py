from enum import Enum

class HeaterState(Enum):
    OFF = 0
    FAN_ONLY = 1
    LOW_HEAT = 2
    FULL_HEAT = 3

    @property
    def pretty_name(self):
        _pretty_names = {
            HeaterState.OFF: 'OFF',
            HeaterState.FAN_ONLY: 'Fan only',
            HeaterState.LOW_HEAT: 'Low Heat',
            HeaterState.FULL_HEAT: 'Full Heat',
        }

        return _pretty_names[self]
        
        # OS signal handler
def handler_stop_signals(signum, frame):
    state.run = False