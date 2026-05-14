void setup() {
  pinMode(11, OUTPUT);
  TCCR2A = _BV(COM2A0) | _BV(COM2B1) | _BV(WGM20);
  TCCR2B = _BV(WGM22) | _BV(CS20);
  OCR2A = 52;
  OCR2B = 50;
}


void loop() {
  pinMode(11, OUTPUT);
  delay(200); 

  pinMode(11, INPUT);
  delay(800);
}


