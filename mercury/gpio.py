from RPi import GPIO
from rotary_class import RotaryEncoder

import atexit

from logging import critical, info, debug

ROTARY_A = 11
ROTARY_B = 7
BUTTON = 13
SPEAKER = 12

GPIO_DEFAULT_INPUTS = {
    'RotaryA': ROTARY_A,
    'RotaryB': ROTARY_B,
    'Button': BUTTON,
    # 'Reset', 22,
}

GPIO_DEFAULT_OUTPUTS = {
    'Speaker': SPEAKER
}

_DEFAULT = object()


def setup_gpio(inputs=_DEFAULT, outputs=_DEFAULT):
    if inputs is _DEFAULT:
        inputs = GPIO_DEFAULT_INPUTS

    if outputs is _DEFAULT:
        outputs = GPIO_DEFAULT_OUTPUTS

    debug('Setting GPIO modes...')

    atexit.register(GPIO.cleanup)

    try:
        GPIO.setmode(GPIO.BOARD)

        for x in inputs:
            GPIO.setup(inputs[x], GPIO.IN)

        for x in outputs:
            GPIO.setup(outputs[x], GPIO.OUT)

    except BaseException as e:
        critical('GPIO init failed. (%s) The program will exit.' % e)
        raise

    # Inputs
    msg = ' '.join('{}={}'.format(key, value)
                   for key, value in inputs.items())

    info('Set GPIO inputs: %s' % msg)

    # Outputs
    msg = ' '.join('{}={}'.format(key, value)
                   for key, value in outputs.items())
    info('Set GPIO outputs: %s' % msg)


# This is the event callback routine to handle events
def switch_event(callback, direction):
    if direction == 1:
        callback(1)
    elif direction == -1:
        callback(-1)
