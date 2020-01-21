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


# define GPIO pins for (optional) push buttons
GPIO.setmode(GPIO.BOARD) # Use physical pin numbering instead of BCM numbering
PIN_NUMBER_SCALE =  7 # scale button
PIN_NUMBER_COLOR = 12 # colour mode button

# define keyboard keys for scale and colour switching
KEY_NUMBER_SCALE = 13 # use Enter key to switch to next magnification level
KEY_NUMBER_COLOR = ord('/') # use "/" key to toggle colour mode
KEY_ESCAPE = 27 # use Escape to quit program


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
def invert():
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
def next_factor():
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


# storing last state of buttons to filter out small spikes from EM noise
button_state = {
    PIN_NUMBER_SCALE: GPIO.HIGH,
    PIN_NUMBER_COLOR: GPIO.HIGH
}

def button_pressed(channel):
    global button_state
    current_state = GPIO.input(channel)
    if current_state != button_state[channel]:
        button_state[channel] = current_state
        if channel == PIN_NUMBER_SCALE and current_state == GPIO.HIGH:
            next_factor()
        elif channel == PIN_NUMBER_COLOR and current_state == GPIO.HIGH:
            invert()
    
# init push button through GPIO
def init_buttons():
    GPIO.setwarnings(False) # Ignore warnings for now
    for channel in button_state:
        state = button_state[channel]
        up_down = GPIO.PUD_UP if state == GPIO.HIGH else GPIO.PUD_DOWN
        GPIO.setup(channel, GPIO.IN, pull_up_down=up_down)
        GPIO.add_event_detect(channel, GPIO.BOTH, callback=button_pressed) 

init_buttons()

# start displaying the default camera view
#proc = subprocess.Popen(['raspivid', '-f', '-t', '9000', '-rot', '180', '-roi', '0.3,0,0.4,0.4'])
proc = subprocess.Popen(RASPIVID)
#print(proc)

# loop forever, or till escape is pressed
char = ' '
try:
    while ord(char) != KEY_ESCAPE:
        # try to read character from stdin
        char = getch()

        if ord(char) == KEY_NUMBER_SCALE:
            next_factor() # switch to next higher zoom factor

        elif ord(char) == KEY_NUMBER_COLOR:
            invert(0) # toggle colour inversion
    
        elif '0' <= char and char <= '9': # use digit keys as scale factor
            if char == '0':
                # 0 is interpreted as 10
                scale(10)
            else:
                # other digits are interpreted as their number
                factor = ord(char) - ord('0')
                scale(factor)
        
        # wait a bit to not block the processor
        time.sleep(DELAY_S)

finally:
    GPIO.cleanup()
    proc.terminate()
