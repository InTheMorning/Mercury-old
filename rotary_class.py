from RPi import GPIO


GPIO_A, GPIO_B, GPIO_BUTTON = (0, 0, 0)


class RotaryEncoder:
    """
    A class to decode mechanical rotary encoder pulses.
    """

    def __init__(self,
                 pinA,
                 pinB,
                 button,
                 callback=None,
                 button_callback=None
                 ):
        """
        Instatiate the class with the two callbacks.
        The callback receives one argument:
        a `delta` that will be either 1 or -1.
        """
        global GPIO_A, GPIO_B, GPIO_BUTTON
        GPIO_A, GPIO_B, GPIO_BUTTON = (pinA, pinB, button)
        self.last_gpio = None
        self.callback = callback
        self.button_callback = button_callback

        self.levA = 0
        self.levB = 0

        GPIO.setup(GPIO_A, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(GPIO_B, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(GPIO_BUTTON, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        GPIO.add_event_detect(GPIO_A, GPIO.BOTH, self._callback)
        GPIO.add_event_detect(GPIO_B, GPIO.BOTH, self._callback)
        GPIO.add_event_detect(
                              GPIO_BUTTON,
                              GPIO.FALLING,
                              self._button_callback,
                              bouncetime=500
                              )

    def _button_callback(self, channel):
        self.button_callback(GPIO.input(channel))

    def _callback(self, channel):
        level = GPIO.input(channel)
        if channel == GPIO_A:
            self.levA = level
        else:
            self.levB = level

        # Debounce.
        if channel == self.last_gpio:
            return

        # If A was the most recent pin set high, it'll be forward
        # if B was the most recent pin set high, it'll be reverse.
        self.last_gpio = channel
        if channel == GPIO_A and level == 1:
            if self.levB == 1:
                self.callback(1)
        elif channel == GPIO_B and level == 1:
            if self.levA == 1:
                self.callback(-1)
