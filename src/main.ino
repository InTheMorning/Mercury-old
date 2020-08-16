#include <Arduino.h>

const long BITS_PER_SECOND = 9600;

int ST2Relay = 2;
int ST1Relay = 4;
int FANRelay = 5;

int red_light_pin= 9;
int green_light_pin = 10;
int blue_light_pin = 11;

int led_brightness = 255; // max is 255
unsigned long thermostat_timeout = 3600000;
unsigned long cooldown = 3600; // fan cooldown after heating
unsigned long previousFanTime = millis();
unsigned long currentMillis = millis();
unsigned long LastMessage = millis();
int currentstate = 0;
int debounce = 500; //time between state changes
unsigned int integerValue=0;  // Max value is 65535
char incomingByte;

void setup()
{
	pinMode(13, OUTPUT);
	pinMode(ST2Relay, OUTPUT);
	pinMode(ST1Relay, OUTPUT);
	pinMode(FANRelay, OUTPUT);
	pinMode(red_light_pin, OUTPUT);
	pinMode(green_light_pin, OUTPUT);
	pinMode(blue_light_pin, OUTPUT);

	digitalWrite(13, LOW);
	digitalWrite(ST2Relay, HIGH);
	digitalWrite(ST1Relay, HIGH);
	digitalWrite(FANRelay, HIGH);

	Serial.begin(BITS_PER_SECOND);

	delay(500);
}

void RGB_color(int red_light_value, int green_light_value, int blue_light_value)
{
	float red = ((red_light_value / 255.0) * led_brightness) + 0.9999;
	float green = ((green_light_value / 255.0) * led_brightness) + 0.9999;
	float blue = ((blue_light_value / 255.0) * led_brightness) + 0.9999;

	analogWrite(red_light_pin, (int) red);
	analogWrite(green_light_pin, (int) green);
	analogWrite(blue_light_pin, (int) blue);
}

int hvacmode(int n)
{
	
	int newstate = 0;
	
	if (n==3) // state 3: full heat
	{
		digitalWrite(ST2Relay, LOW);
		digitalWrite(ST1Relay, LOW);
		digitalWrite(FANRelay, HIGH);
		RGB_color(255,0,0);
		newstate = 3;
	}

	else if (n==2) // state 2: low heat
	{
		digitalWrite(ST2Relay, HIGH);
		digitalWrite(ST1Relay, LOW);
		digitalWrite(FANRelay, HIGH);
		RGB_color(255,80,0);
		newstate = 2;
	}

	else if (n==1) // state 1: fan only
	{
		digitalWrite(ST2Relay, HIGH);
		digitalWrite(ST1Relay, HIGH);
		digitalWrite(FANRelay, LOW);
		RGB_color(0,255,0);
		previousFanTime = (unsigned long) millis();
		newstate = 1;
	}

	else if ((currentstate>1) && (currentstate<4))
	{
		digitalWrite(ST2Relay, HIGH);
		digitalWrite(ST1Relay, HIGH);
		digitalWrite(FANRelay, LOW);
		RGB_color(0,255,0);
		previousFanTime = (unsigned long) millis();
		newstate = 1;
	}

	else if ((n==0) && (currentstate != 1))
	{
		digitalWrite(ST2Relay, HIGH);
		digitalWrite(ST1Relay, HIGH);
		digitalWrite(FANRelay, HIGH);
		RGB_color(2,2,3);
		newstate = 0;
	}

	else
	{
		newstate = currentstate;
	}
	
	delay(debounce);
	return newstate;
}

void loop()
{
	currentMillis = (unsigned long) millis();

	if (Serial.available() > 0)
	{
		// something came across serial
		
		integerValue = 0;         // throw away previous integerValue
		while(1)
		{            // force into a loop until 'n' is received
			incomingByte = Serial.read();
			if (incomingByte == '\n') break;   // exit the while(1), we're done receiving
			if (incomingByte == -1) continue;  // if no characters are in the buffer read() returns -1
			integerValue *= 10;  // shift left 1 decimal place
			// convert ASCII to integer, add, and shift left 1 decimal place
			integerValue = ((incomingByte - 48) + integerValue);
		}

		LastMessage = currentMillis;

		if (integerValue == 9)
		{
			delay(50);
			Serial.println(currentstate);  // report current state
		}
		else
		{
			currentstate = hvacmode(integerValue);
		}
 
		delay(10);
	}
	if (currentstate == 1
	    && ((currentMillis - previousFanTime) >= cooldown))
	{
		currentstate = 0;
		currentstate = hvacmode(0);
	}

	else if (currentstate > 1 && ((currentMillis - LastMessage) >= thermostat_timeout))
	{
		currentstate = hvacmode(0);
	}

	else
	{
		delay(10);
	}
}
