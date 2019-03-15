#!/usr/bin/python3
# load a program from command line, wait for button/key press event on raspi and
# react by closing the previously launched program and re-opening it with a
# different parameter
import RPi.GPIO as GPIO        # Import Raspberry Pi GPIO library (for external button)
import subprocess              # Import subprocess to start camera view in background
import sys, termios, tty, time # for character input from command line

# you can adapt this script to your specific setup, by setting either
# DISTANCE_TO_SURFACE_CM or DEFAULT_WIDTH_CM to your local measurements
# WIDTHS_CM or SCALE_FACTORS can be modified for a fixed set of scale factors
# PIN_NUMBER_... can be changed if you connect buttons to different GPIO pins

# distance in cm between camera objective and the surface (e.g. table)
# adapt this to your setup, or directly set the value DEFAULT_WIDTH_CM below
DISTANCE_TO_SURFACE_CM = 24.5

# visible width when calling "raspivid -f -rot 180" (measure with a ruler)
# adapt this to your setup, as it depends on the camera and screen
DEFAULT_WIDTH_CM = DISTANCE_TO_SURFACE_CM * 0.67
# uncomment the following line to overwrite with your own measured value
# DEFAULT_WIDTH_CM = 16.5

# typical line widths to cycle through by pressing the scale button / enter
# set your desired line widths here, e.g. from the newspaper, typical books or magazines
WIDTHS_CM = [DEFAULT_WIDTH_CM, 12.5, 9, 5]


# magnification when calling raspivid without parameters
# value is from my initial setup, matters only if you set SCALE_FACTORS manually
DEFAULT_FACTOR = 2.5

# pre-defined scale factors to cycle through with button/enter
SCALE_FACTORS = [DEFAULT_FACTOR * DEFAULT_WIDTH_CM / x for x in WIDTHS_CM]
# uncomment the following line if you rather want to define the scale factors manually
# SCALE_FACTORS = [DEFAULT_FACTOR, 5, 10]

factor = SCALE_FACTORS[0]  # use first entry as initial factor on boot up


PIN_NUMBER_SCALE = 10 # physical pin number of GPIO for scale button
PIN_NUMBER_COLOR =  8 # physical pin number of GPIO for colour mode

BOUNCE_TIME_MS = 300   # ms to wait till a new button event is generated (avoid double click artefacts)
DELAY_S = 0.01        # s to sleep between polling the keyboard

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

# toggle -ifx parameter between normal colours and inverted colours
def invert(channel):
    global factor
    global RASPIVID
    if '-ifx' in RASPIVID:
        i = RASPIVID.index('-ifx')
        RASPIVID[i + 1] = 'negative' if RASPIVID[i + 1] == 'none' else 'none'
        # reload with toggled image effect
        scale(factor)

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
    
    # Set pin for scale button to be an input pin and set initial value to be pulled low (off)
    GPIO.setup(PIN_NUMBER_SCALE, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    # Setup event on rising edge, ignore additional signals in under BOUNCE_TIME_MS ms
    GPIO.add_event_detect(PIN_NUMBER_SCALE, GPIO.RISING, callback=nextFactor, bouncetime=BOUNCE_TIME_MS) 
    
    
    # Set pin for colour invert button to be an input pin and set initial value to be pulled low (off)
    GPIO.setup(PIN_NUMBER_COLOR, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    # Setup event on rising edge, ignore additional signals in under BOUNCE_TIME_MS ms
    GPIO.add_event_detect(PIN_NUMBER_COLOR, GPIO.RISING, callback=invert, bouncetime=BOUNCE_TIME_MS)



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
    elif char == '/':
        invert(0)
        
    # wait a bit to not block the processor
    time.sleep(DELAY_S)


GPIO.cleanup() # Clean up
proc.terminate()