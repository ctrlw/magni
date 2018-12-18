#!/usr/bin/python3
# load a program from command line, wait for button/key press event on raspi and
# react by closing the previously launched program and re-opening it with a
# different parameter
import RPi.GPIO as GPIO        # Import Raspberry Pi GPIO library (for external button)
import subprocess              # Import subprocess to start camera view in background
import sys, termios, tty, time # for character input from command line


# magnification when calling raspivid without parameters
# adapt this value to your screen, by measuring the default scale factor with 2 rulers
DEFAULT_FACTOR = 2.5

# pre-defined scale factors (press button/enter for next), should be in ascending order
SCALE_FACTORS = [DEFAULT_FACTOR, 5, 10]
factor = SCALE_FACTORS[0]  # use first entry as initial factor on boot up


PIN_NUMBER = 10   # physical pin number of GPIO used for button
BOUNCE_TIME = 300 # ms to wait till a new button event is generated (avoid double click artefacts)
DELAY = 0.01      # s to sleep between polling the keyboard

# default view of raspivid without specific scaling
# raspivid -f -t 0 -rot 180
# -f is full screen
# -t gets a timeout value in ms (0 for no timeout)
# -rot is rotation, depends on the way the camera is mounted
# -ifx controls image effects, allows e.g. colour inversion
RASPIVID = ['raspivid', '-f', '-t', '0', '-rot', '180', '-ifx', 'none']


# read a single character, taken from http://code.activestate.com/recipes/134892/
def getch():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch


# convert a scale factor to the values needed by raspivid's roi parameter
def scale2roi(scale_factor):
    diameter = DEFAULT_FACTOR / scale_factor
    radius = diameter / 2
    start = 0.5 - radius
    
    # assure that values are in allowed range (e.g. factor 1 is not supported on bigger screens)
    start = max(start, 0)
    diameter = min(diameter, 1)
    
    # y value is always 0, to have the same upper position regardless of scale factor ()
    roi = "%.2f,%.2f,%.2f,%.2f" % (start, 0, diameter, diameter)
    return roi
    

# react on button pressed
def nextFactor(channel):
    global factor
        
    # find the highest entry in SCALE_FACTORS that is <= current factor
    # if the current factor is less (due to direct factor input), switch to default value
    same_or_less = [v for v in SCALE_FACTORS if v <= factor]
    if len(same_or_less) == 0:
        factor = DEFAULT_FACTOR
    else:
        # step to next scale factor, after last entry go back to first
        closest_factor = max(same_or_less)
        i = SCALE_FACTORS.index(closest_factor)
        i_next = (i + 1) % len(SCALE_FACTORS)
        factor = SCALE_FACTORS[i_next]
    
    scale(factor)
    
    
# change to given scale factor
def scale(new_factor):
    global proc
    global factor
    
    factor = max(new_factor, DEFAULT_FACTOR)
    
    #print("Scale factor", factor)

    # terminate current camera view, to restart with a different scale factor
    proc.terminate()
    # @TODO: wait till it's really terminated
    
    # convert factor to raspivid's -roi parameters
    roi = scale2roi(factor)

    # start with new scale factor
    #print(RASPIVID + ['-roi', roi])
    proc = subprocess.Popen(RASPIVID + ['-roi', roi])
    #print("Started new process", proc)
    
    
# push button through GPIO
def initPushbutton():    
    GPIO.setwarnings(False) # Ignore warning for now
    GPIO.setmode(GPIO.BOARD) # Use physical pin numbering
    GPIO.setup(PIN_NUMBER, GPIO.IN, pull_up_down=GPIO.PUD_DOWN) # Set pin 10 to be an input pin and set initial value to be pulled low (off)

    GPIO.add_event_detect(PIN_NUMBER, GPIO.RISING, callback=nextFactor, bouncetime=BOUNCE_TIME) # Setup event on pin 10 rising edge, ignore additional signals in under BOUNCE_TIME ms



initPushbutton()

# start displaying the default camera view
#proc = subprocess.Popen(['raspivid', '-f', '-t', '9000', '-rot', '180', '-roi', '0.3,0,0.4,0.4'])
proc = subprocess.Popen(RASPIVID)
#print(proc)

# loop forever, or till escape is pressed
char = ' '
ENTER_KEY = 13
ESCAPE_KEY = 27
while ord(char) != ESCAPE_KEY:
    # try to read character from stdin
    char = getch()
    
    # pressing a digit key will use its value as the scale factor
    if '0' <= char and char <= '9':
        if char == '0':
            # 0 is interpreted as 10
            scale(10)
        else:
            # other digits are interpreted as their number
            factor = ord(char) - ord('0')
            scale(factor)

    # pressing enter switches to next higher zoom factor, same as pressing the push button
    elif ord(char) == ENTER_KEY:
        nextFactor('')
        
    # pressing '/' toggles colour inversion
    elif char == '/' and '-ifx' in RASPIVID:
        i = RASPIVID.index('-ifx')
        if RASPIVID[i + 1] == 'none':
            RASPIVID[i + 1] = 'negative'
        else:
            RASPIVID[i + 1] = 'none'
        # reload with toggled image effect
        scale(factor)
        
    # wait a bit to not block the processor
    time.sleep(DELAY)


GPIO.cleanup() # Clean up
proc.terminate()