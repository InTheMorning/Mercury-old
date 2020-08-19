#include <Arduino.h>

const long BITS_PER_SECOND = 9600;

const int stage_2_relay = 2;
const int stage_1_relay_pin = 4;
const int fan_relay_pin = 5;
const int red_light_pin= 9;
const int green_light_pin = 10;
const int blue_light_pin = 11;

// in milliseconds
const unsigned long serial_timeout = 1000;
const unsigned long thermostat_timeout = 600000;
const unsigned long warmup_timeout = 300000; // heater warmup before full heat
const unsigned long cooldown_timeout = 300000; // fan cooldown after heating
int led_brightness = 128; // max is 255

const int debounce = 500; // minimum time between state changes

// actual state of the heater relays
int current_relay_state = -1;

// operating state of the controller
int current_mode = 0;
int target_mode = -1;

char *status_strings[] = 
	{
	"Off",
	"Fan",
	"Low heat",
	"High heat",
	"Warming up",
	"Cooling down"
	};

unsigned long message_timestamp = 0;
unsigned long state_change_timestamp = 0;
unsigned long start_warmup_timestamp = 0;
unsigned long start_cooldown_timestamp = 0;

void reset_timestamp(unsigned long *timeStamp)
{
	*timeStamp = millis();
}

void rgb_color(int redValue, int greenValue, int blueValue)
{
	float Red = ((redValue / 255.0) * led_brightness) + 0.9999;
	float Green = ((greenValue / 255.0) * led_brightness) + 0.9999;
	float Blue = ((blueValue / 255.0) * led_brightness) + 0.9999;

	analogWrite(red_light_pin, (int) Red);
	analogWrite(green_light_pin, (int) Green);
	analogWrite(blue_light_pin, (int) Blue);
}

int int_from_serial()
// returns an int from serial
{
		char integerValue = 0;      // throw away previous integerValue
        unsigned long serialTimestamp = millis();
		while(1)
        // force into a loop until 'n' is received or serial_timeout expires
		{
            if (millis() - serialTimestamp < serial_timeout)
            {
                char incomingByte = Serial.read();
                if (incomingByte == '\n') break;   // exit the while(1), we're done receiving
                if (incomingByte == -1) continue;  // if no characters are in the buffer read() returns -1
                integerValue *= 10;  // shift left 1 decimal place
                // convert ASCII to integer, add, and shift left 1 decimal place
                integerValue = ((incomingByte - 48) + integerValue);
            }
            else
            {
                return -1;
            }            
		}
        return integerValue;
}

void set_hvac_state(int n)
// relay and led definitions for hvac states
{
	if (n == current_relay_state)
	// do nothing
	{
		return;
	}
	
    else if (n == 3)
	// state 3: full heat
	{
		digitalWrite(stage_2_relay, LOW);
		digitalWrite(stage_1_relay_pin, LOW);
		digitalWrite(fan_relay_pin, HIGH);
		rgb_color(255,0,0);
        current_relay_state = 3;
	}

	else if (n == 2)
	// state 2: low heat
	{
		digitalWrite(stage_2_relay, HIGH);
		digitalWrite(stage_1_relay_pin, LOW);
		digitalWrite(fan_relay_pin, HIGH);
		rgb_color(255,80,0);
		current_relay_state = 2;
	}

	else if (n == 1)
	// state 1: fan only
	{
		digitalWrite(stage_2_relay, HIGH);
		digitalWrite(stage_1_relay_pin, HIGH);
		digitalWrite(fan_relay_pin, LOW);
		rgb_color(0,255,0);
		current_relay_state = 1;
	}

	else if (n == 0)
	// state 0: off
	{
		digitalWrite(stage_2_relay, HIGH);
		digitalWrite(stage_1_relay_pin, HIGH);
		digitalWrite(fan_relay_pin, HIGH);
		rgb_color(2,2,3);
		current_relay_state = 0;
	}
    else
    {
        return;
    }
	reset_timestamp(&state_change_timestamp);
	delay(debounce);
}

void receive_hvac_command(int n)
// handle incoming request
{
    if (current_mode == 0 || current_mode == 1)
	{
		if (n == 0 || n == 1)
		{
			// allow toggle if different
			if (current_mode != n)
			{
				set_hvac_state(n);
				current_mode = n;
			}
		}
		else if (n == 2 || n == 3)
		{
			// require warmup
			reset_timestamp(&start_warmup_timestamp);
			set_hvac_state(2);
			current_mode = 4;
			target_mode = n;
		}
	}
	else if (current_mode == 2 || current_mode == 3)
	{
		if (n == 0 || n == 1)
		{
			// require cooldown
			reset_timestamp(&start_cooldown_timestamp);
			set_hvac_state(1);
			current_mode = 5;
			target_mode = n;
		}
		else if (n == 2 || n == 3)
		{
			// allow toggle if different
			if (current_mode != n)
			{
				set_hvac_state(n);
				current_mode = n;
			}
		}
	}
	else if (current_mode == 4)
	{
		if (n == 2)
		{
			// cancel warmup
			set_hvac_state(n);
			current_mode = n;
		}
	}
	
	else if (current_mode == 5)
	{
		if (n == 2)
		{
			// cancel cooldown
			set_hvac_state(n);
			current_mode = n;
		}
	}
}

void emergency_mode_loop()
{
	receive_hvac_command(0);
}

void warmup_mode_loop(int t)
{
	// check if we should exit this mode
	if (millis() - start_warmup_timestamp > warmup_timeout)
	{
		set_hvac_state(t);
		current_mode = t;
	}
}

void cooldown_mode_loop(int t)
{
	// check if we should exit this mode
	if (millis() - start_cooldown_timestamp > cooldown_timeout)
	{
		set_hvac_state(t);
		current_mode = t;
	}
}

void monitor_serial()
// monitor the serial connection, and either respond or initiate a hvac state request
{
    if (Serial.available() > 0)
    {
	    int serialRequest = int_from_serial();
        
        if (serialRequest == 10)
		{
        	// special code to retrieve current mode via serial
			delay(50);
			Serial.println(status_strings[current_mode]);
		}
		else if (serialRequest == 11)
		{
        	// special code to retrieve heater state via serial
			delay(50);
			Serial.println(current_relay_state);
		}
        
        else if (serialRequest < 0 || serialRequest > 3)
        // if we timed out(-1), or the integer is invalid
        {
            return; // don't do anything
        }

        else
		{
			receive_hvac_command(serialRequest);
		}
        
        reset_timestamp(&message_timestamp);
    }
}

void setup()
{
    // builtin led
	pinMode(13, OUTPUT);
    
    // relays
	pinMode(stage_2_relay, OUTPUT);
	pinMode(stage_1_relay_pin, OUTPUT);
	pinMode(fan_relay_pin, OUTPUT);
    
    // color led
	pinMode(red_light_pin, OUTPUT);
	pinMode(green_light_pin, OUTPUT);
	pinMode(blue_light_pin, OUTPUT);

	// turn everything off
    digitalWrite(13, LOW);
    set_hvac_state(0);
    
	//start serial connection
    Serial.begin(BITS_PER_SECOND);
    
    reset_timestamp(&message_timestamp);
}

void loop()
{
	monitor_serial();
	
	// check if we are abandoned
	if (millis() - message_timestamp > thermostat_timeout)
	{
		emergency_mode_loop();
	}
	
	// also check if we are in transition
	if (current_mode == 4)
	// warming up
	{
		warmup_mode_loop(target_mode);
	}
	else if (current_mode == 5)
	// cooling down
	{
		cooldown_mode_loop(target_mode);
	}
}
