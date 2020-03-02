from enum import Enum
from logging import critical, error
from RPi import GPIO
from time import sleep

import atexit


class Sound(Enum):
    TIC = 0
    BEEP = 1
    BONK = 2
    CRITICAL = 3


def setup_tone_player(speaker_pin, magic_number=600):
    try:
        GPIO.setup(speaker_pin, GPIO.OUT)

        p = GPIO.PWM(speaker_pin, magic_number)
        p.start(0)
    except BaseException:
        critical('Could not initialize PWM')
        raise

    tone_player.p = p
    atexit.register(destroy_tone_player, p)


def destroy_tone_player(p):
    p.stop()


def tone_player(tone):
    p = getattr(tone_player, 'p', None)

    if not p:
        error('Speaker must be initialized before use!')
        return

    if tone == Sound.TIC:
        p.ChangeFrequency(50)
        p.ChangeDutyCycle(100)
        sleep(0.01)

    elif tone == Sound.BEEP:
        p.ChangeFrequency(880)
        p.ChangeDutyCycle(100)
        sleep(0.05)

    elif tone == Sound.BONK:
        p.ChangeFrequency(220)
        p.ChangeDutyCycle(50)
        sleep(0.05)

    elif tone == Sound.CRITICAL:
        for i in range(4):
            tone_player(Sound.BEEP)

    p.ChangeDutyCycle(0)
