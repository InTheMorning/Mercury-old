#include <Arduino.h>
#define relayON LOW
#define relayOFF HIGH
#define BITS_PER_SECOND 9600
#define coils_offset 1000
#define fan_relay_pin 2
#define fan_speed_relay_pin 3
#define stage_1_relay_pin 4
#define stage_2_relay_pin 7
#define red_light_pin 9
#define green_light_pin 10
#define blue_light_pin 11


const unsigned long thermostat_timeout = (60000 * 15); // emergency mode trigger (minutes)
const unsigned long preheat_timeout = (1000 * 5); // preheat before blower (seconds)
const unsigned long warmup_timeout = (1000 * 30); // warmup before full heat (seconds)
const unsigned long cooldown_timeout = (1000 * 20); // fan cooldown after heating (seconds)
const unsigned char led_max_brightness = 222; // max is 255


// operating state of the controller
int current_mode = -1;
int target_mode = -1; // used when in a temporary mode

char *status_strings[] = 
	{
	"Off",
	"Fan",
	"Low heat",
	"High heat",
	"Pre-heating",
	"Warming up",
	"Cooling down"
	};

unsigned long message_timestamp = 0;
unsigned long state_change_timestamp = 0;
unsigned long start_warmup_timestamp = 0;
unsigned long start_preheat_timestamp = 0;
unsigned long start_cooldown_timestamp = 0;

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
		
		if (r < 256 && g < 256 && b < 256)
		{	// save provided color values
			Red = (unsigned char) r;
			Green = (unsigned char) g;
			Blue = (unsigned char) b;
		}
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
	if (n == 5)
	{
		// state 5: prepare full heat
		digitalWrite(fan_relay_pin, relayON);
		digitalWrite(fan_speed_relay_pin, relayOFF);
		digitalWrite(stage_1_relay_pin, relayON);
		digitalWrite(stage_2_relay_pin, relayON);
		led_control(255,20,0);
	}
	else if (n == 4)
	{
		// state 4: preheat
		digitalWrite(fan_relay_pin, relayOFF);
		digitalWrite(fan_speed_relay_pin, relayOFF);
		digitalWrite(stage_1_relay_pin, relayON);
		digitalWrite(stage_2_relay_pin, relayOFF);
		led_control(255,80,0);
	}
    else if (n == 3)
	{
		// state 3: full heat
		digitalWrite(fan_relay_pin, relayON);
		digitalWrite(fan_speed_relay_pin, relayON);
		digitalWrite(stage_1_relay_pin, relayON);
		digitalWrite(stage_2_relay_pin, relayON);
		led_control(255,0,0);
	}

	else if (n == 2)
	{
		// state 2: low heat
		digitalWrite(fan_relay_pin, relayON);
		digitalWrite(fan_speed_relay_pin, relayOFF);
		digitalWrite(stage_1_relay_pin, relayON);
		digitalWrite(stage_2_relay_pin, relayOFF);
		led_control(255,80,0);
	}

	else if (n == 1)
	{
		// state 1: fan only
		digitalWrite(fan_relay_pin, relayON);
		digitalWrite(fan_speed_relay_pin, relayOFF);
		digitalWrite(stage_1_relay_pin, relayOFF);
		digitalWrite(stage_2_relay_pin, relayOFF);
		led_control(0,255,0);
	}

	else if (n == 0)
	// state 0: off
	{
		digitalWrite(fan_relay_pin, relayOFF);
		digitalWrite(fan_speed_relay_pin, relayOFF);
		digitalWrite(stage_1_relay_pin, relayOFF);
		digitalWrite(stage_2_relay_pin, relayOFF);
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
	return current_relay_state;
}


void command_hvac(int n)
// handle incoming request
{
	if (current_mode == n)
	{
		return;
	}
	else if (current_mode == 0) 
	{
		if (n == 1)
		{
			// allow toggle fan on
			allow_toggle(n);
		}
		else if (n == 2 || n == 3)
		{
			require_preheat(n);
		}
	}
	else if (current_mode == 1)
	{
		if (n == 0 || n == 2)
		{
			// allow toggle off or heat
			allow_toggle(n);
		}
		else if (n == 3)
		{
			require_warmup();
		}
	}
	else if (current_mode == 2 || current_mode == 3 || current_mode == 4)
	{
		if (n == 0 || n == 1)
		{
			require_cooldown(n);
		}
		else if (n == 2)
		{
			allow_toggle(n);
		}
		else if (n == 3)
		{
			require_warmup();
		}
	}
	else if (current_mode == 5)
	{
		if (n == 2)
		{
			// cancel warmup
			allow_toggle(n);
		}
	}
	else if (current_mode == 6)
	{
		if (n == 2)
		{
			// cancel cooldown
			allow_toggle(n);
		}
	}
}

void require_preheat(int t) // target state
{
	start_preheat_timestamp = millis();
	set_hvac_state(4);
	current_mode = 4;
	target_mode = t;
}

void require_warmup()
{
	start_warmup_timestamp = millis();
	if (set_hvac_state(-1) != 2)
	{
		set_hvac_state(2);
		delay(coils_offset);
	}
	set_hvac_state(5);
	current_mode = 5;
	target_mode = 3;
}
	
void require_cooldown(int t) // target state
{
	// require cooldown
	start_cooldown_timestamp = millis();
	set_hvac_state(1);
	current_mode = 6;
	target_mode = t;
}

void allow_toggle(int t)
{
	set_hvac_state(t);
	current_mode = t;
	target_mode = t;
}

void emergency_mode_loop()
{
	if (monitor_serial() == false)
	{
		command_hvac(0);
		led_control(-1, -1, -1);
	}
	else
	{
		// reset led brightness
		led_control(256, 256, 256);
	}
	
}

void preheat_mode_loop(int t)
{
	// flash the led
	led_control(-1, -1, -1);

	// check if we should exit this mode
	if (millis() - start_preheat_timestamp > preheat_timeout)
	{
		if (t == 2)
		{
			allow_toggle(t);
		}
		else
		{
			require_warmup();
		}
	}
}
void warmup_mode_loop(int t)
{
	// flash the led
	led_control(-1, -1, -1);

	// check if we should exit this mode
	if (millis() - start_warmup_timestamp > warmup_timeout)
	{
		allow_toggle(t);
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

bool monitor_serial()
// monitor the serial connection, and either respond or initiate a hvac state request
{
    if (Serial.available() > 0)
    {
	    int serialRequest = int_from_serial();
        
        if (serialRequest == 10)
		{
        	// special code to retrieve current mode via serial
			delay(5);
			Serial.println(status_strings[current_mode]);
		}
		else if (serialRequest == 11)
		{
        	// special code to retrieve heater state via serial
			delay(5);
			Serial.println(set_hvac_state(-1));
		}
        
        else if (serialRequest < 0 || serialRequest > 3)
        // if we timed out(-1), or the integer is invalid
        {
            return false; // don't do anything
        }

        else
		{
			command_hvac(serialRequest);
			// Acknowledge command reception
			Serial.println(target_mode);
		}
        
        message_timestamp = millis();
		return true;
    }
	else
	{
		return false;
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
	allow_toggle(0);
	  
	//start serial connection
    Serial.begin(BITS_PER_SECOND);
    
    message_timestamp = millis();
}

void loop()
{
	// check if we are in a lockout state
	
	if (current_mode == 4)
	{
		// preheating
		preheat_mode_loop(target_mode);
		monitor_serial();
	}
	else if (current_mode == 5)
	{
		// warming up
		warmup_mode_loop(target_mode);
		monitor_serial();
	}
	else if (current_mode == 6)
	{
		// cooling down
		cooldown_mode_loop(target_mode);
		monitor_serial();
	}
	
	else if (millis() - message_timestamp > thermostat_timeout)
	{
		// if we are abandoned

		emergency_mode_loop();
	}
	else
	{
		monitor_serial();
	}
	
}
