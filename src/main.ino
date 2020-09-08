#include <Arduino.h>

const long BITS_PER_SECOND = 9600;

const unsigned char fan_relay_pin = 2;
const unsigned char fan_speed_relay_pin = 3;
const unsigned char stage_1_relay_pin = 4;
const unsigned char stage_2_relay_pin = 5;
const unsigned char red_light_pin = 9;
const unsigned char green_light_pin = 10;
const unsigned char blue_light_pin = 11;

const unsigned long thermostat_timeout = (60000 * 15); // emergency mode trigger
const unsigned long warmup_timeout = (60000 * 5); // warmup before full heat
const unsigned long cooldown_timeout = (1000 * 90); // fan cooldown after heating
const unsigned char led_max_brightness = 196; // max is 255


// operating state of the controller
int current_mode = 0;
int target_mode = -1; // used when in a temporary mode

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
\
void led_control(int r, int g, int b)
{
	static unsigned char Red, Green, Blue; // current color
	static unsigned char Brightness; // current brightness
	static unsigned int Phase; // phase of waveform in degrees
	static unsigned long Timestamp;
	
	float brightness_multiplier;
	
	// if any values are negative, just step the brightness
	if (r < 0 || g < 0 || b < 0) 
	{
		if (millis() - Timestamp >= 15)
		{
			// wrap around phase
			if (Phase >= 360)
			{
				Phase = 0;
			}

			// obtain multiplier from wave function
			float brightness_multiplier = ((1 + cos(Phase * 3.141592 / 180.0)) / 2.0);
			// brightness_multiplier = Phase;
			
			// modify the brightness
			Brightness = (unsigned char) (brightness_multiplier * led_max_brightness) + 0.5;

			// Avoid blackout
			if (Brightness < 1)
			{
				Brightness = 1;
			}
			
			// increment the phase
			Phase += 5;
			Timestamp = millis();
			
			led_write(Red, Green, Blue, Brightness);
		}
	}
	
	else
	{
		// reset the phase and brightness
		Phase = 0;
		Brightness = led_max_brightness;
		
		// save provided color values
		Red = (unsigned char) r;
		Green = (unsigned char) g;
		Blue = (unsigned char) b;
		led_write(Red, Green, Blue, Brightness);
	}
}

void led_write(unsigned char r, unsigned char g, unsigned char b, unsigned char brightness)
{
	// compute the new r,g,b values
	float rv = (r / 255.0 * brightness) + 0.5;
	float gv = (g / 255.0 * brightness) + 0.5;
	float bv = (b / 255.0 * brightness) + 0.5;
	// write to led
	analogWrite(red_light_pin, (unsigned char) rv);
	analogWrite(green_light_pin, (unsigned char) gv);
	analogWrite(blue_light_pin, (unsigned char) bv);
}

int int_from_serial()
// returns an int from serial
{
		char integerValue = 0;      // throw away previous integerValue
        unsigned long serialTime = millis();
		
		// force into a loop until 'n' is received
		while(1)
		{
			char incomingByte = Serial.read();
			if (incomingByte == '\n') break;   // exit the while(1), we're done receiving
			if (incomingByte == -1) continue;  // if no characters are in the buffer read() returns -1
			integerValue *= 10;  // shift left 1 decimal place
			// convert ASCII to integer, add, and shift left 1 decimal place
			integerValue = ((incomingByte - 48) + integerValue);
		}
        return integerValue;
}

int set_hvac_state(int n)
// relay and led definitions for hvac heating states
{
	static int current_relay_state;
	
	if (n == current_relay_state)
	{
		// do nothing
		return current_relay_state;
	}
	else if (n == 4)
	{
		// state 4: prepare full heat
		digitalWrite(fan_relay_pin, HIGH);
		digitalWrite(fan_speed_relay_pin, HIGH);
		digitalWrite(stage_1_relay_pin, LOW);
		digitalWrite(stage_2_relay_pin, LOW);
		led_control(255,20,0);
	}
    else if (n == 3)
	{
		// state 3: full heat
		digitalWrite(fan_relay_pin, HIGH);
		digitalWrite(fan_speed_relay_pin, LOW);
		digitalWrite(stage_1_relay_pin, LOW);
		digitalWrite(stage_2_relay_pin, LOW);
		led_control(255,0,0);
	}

	else if (n == 2)
	{
		// state 2: low heat
		digitalWrite(fan_relay_pin, HIGH);
		digitalWrite(fan_speed_relay_pin, HIGH);
		digitalWrite(stage_1_relay_pin, LOW);
		digitalWrite(stage_2_relay_pin, HIGH);
		led_control(255,80,0);
	}

	else if (n == 1)
	{
		// state 1: fan only
		digitalWrite(fan_relay_pin, LOW);
		digitalWrite(fan_speed_relay_pin, HIGH);
		digitalWrite(stage_1_relay_pin, HIGH);
		digitalWrite(stage_2_relay_pin, HIGH);
		led_control(0,255,0);
	}

	else if (n == 0)
	// state 0: off
	{
		digitalWrite(fan_relay_pin, HIGH);
		digitalWrite(fan_speed_relay_pin, HIGH);
		digitalWrite(stage_1_relay_pin, HIGH);
		digitalWrite(stage_2_relay_pin, HIGH);
		led_control(8,8,12);
	}
    else
    {
		// invalid, no state change
        return current_relay_state;
    }
	// state changed
	current_relay_state = n;
	state_change_timestamp = millis();
	delay(10);
	return current_relay_state;
}


void command_hvac(int n)
// handle incoming request
{
	if (current_mode == 0 || current_mode == 1)
	{
		if (n == 0 || n == 1)
		{
			// allow toggle fan on/off
			if (current_mode != n)
			{
				allow_toggle(n);
			}
		}
		else if (n == 2 || n == 3)
		{
			require_warmup(2, n);
		}
	}
	else if (current_mode == 2 || current_mode == 3)
	{
		if (n == 0 || n == 1)
		{
			require_cooldown(n);
		}
		else if (n == 2 && current_mode != n)
		{
			// allow toggle if different
			allow_toggle(n);
		}
		else if (n == 3 && current_mode != n)
		{
			require_warmup(4, n);
		}
	}
	else if (current_mode == 4)
	{
		if (n == 2)
		{
			// cancel warmup
			allow_toggle(n);
		}
	}
	else if (current_mode == 5)
	{
		if (n == 2)
		{
			// cancel cooldown
			allow_toggle(n);
		}
	}
}

void require_warmup(int newstate, int t)
{
	start_warmup_timestamp = millis();
	set_hvac_state(newstate);
	current_mode = 4;
	target_mode = t;
}
	
void require_cooldown(int t)
{
	// require cooldown
	start_cooldown_timestamp = millis();
	set_hvac_state(1);
	current_mode = 5;
	target_mode = t;
}

void allow_toggle(int t)
{
	set_hvac_state(t);
	current_mode = t;
}

void emergency_mode_loop()
{
	led_control(-1, -1, -1);
	command_hvac(0);
}

void warmup_mode_loop(int t)
{
	// flash the led
	led_control(-1, -1, -1);

	// check if we should exit this mode
	if (millis() - start_warmup_timestamp > warmup_timeout)
	{
		int cm = set_hvac_state(-1);
		
		if (cm >= t)
		{
			allow_toggle(t);
		}
		else
		{
			require_warmup(4, t);
		}
	}
}

void cooldown_mode_loop(int t)
{
	// flash the led
	led_control(-1, -1, -1);

	// check if we should exit this mode
	if (millis() - start_cooldown_timestamp > cooldown_timeout)
	{
		current_mode = 1;
		command_hvac(t);
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
			Serial.println(set_hvac_state(-1));
		}
        
        else if (serialRequest < 0 || serialRequest > 3)
        // if we timed out(-1), or the integer is invalid
        {
            return; // don't do anything
        }

        else
		{
			command_hvac(serialRequest);
		}
        
        message_timestamp = millis();
    }
}

void setup()
{
    // builtin led
	pinMode(13, OUTPUT);
    
    // relays
	pinMode(stage_2_relay_pin, OUTPUT);
	pinMode(stage_1_relay_pin, OUTPUT);
	pinMode(fan_relay_pin, OUTPUT);
    pinMode(fan_speed_relay_pin, OUTPUT);
	
    // color led
	pinMode(red_light_pin, OUTPUT);
	pinMode(green_light_pin, OUTPUT);
	pinMode(blue_light_pin, OUTPUT);

	// turn everything off
    digitalWrite(13, LOW);
	digitalWrite(fan_relay_pin, HIGH);
	digitalWrite(fan_speed_relay_pin, HIGH);
	digitalWrite(stage_1_relay_pin, HIGH);
	digitalWrite(stage_2_relay_pin, HIGH);
	led_control(8,8,12);
	  
	//start serial connection
    Serial.begin(BITS_PER_SECOND);
    
    message_timestamp = millis();
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
