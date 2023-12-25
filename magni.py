#!/usr/bin/python3
# Open camera preview, wait for button/key press event on raspi and react by
# adapting camera parameters
import asyncio
from datetime import datetime
import evdev                   # for input from mouse and command line
from gpiozero import Button    # for external buttons

# load available camera lib (picamera on legacy, picamera2 on newer OS) 
try:
    from picamera import PiCamera  # Import camera functions
    print("Using picamera")
except ImportError:
    pass
try:
    from picamera2 import Picamera2, Preview, MappedArray
    from libcamera import controls, Transform
    print("Using picamera2 and libcamera")
except ImportError:
    pass

import os                      # for background OCR and TTS process
import re                      # for parsing fbset output
import signal                  # to kill background process 
import subprocess              # for calling fbset to detect screen resolution and readout

# You can adapt this script to your specific setup, by changing the constants 
# SCALE_FACTORS can be modified for a fixed set of scale factors
# PIN_NUMBER_... can be changed if you connect buttons to different GPIO pins

# Picamera2 needs the screen resolution for preview
# Default is full HD, will try to read actual values in init_camera
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080

# Rotate view by 180 degrees for the typical use-case with camera behind object
ROTATION = 180

# Distance in cm between camera objective and the surface (e.g. table)
# Adapt this if you have a camera v3 in fixed setup and want to fix the focus
# The default None will run autofocus on each change of magnification
DISTANCE_TO_SURFACE_CM = None # replace with your distance, e.g. 24.5

# Pre-defined scale factors to cycle through with button/enter
# These factors are camera pixels to screen pixels ratio, the actual
# magnification depends also on the camera, the screen size and the distance
# between camera and object
DEFAULT_FACTOR = 1.5
SCALE_FACTORS = [DEFAULT_FACTOR, 3, 4.5, 8]
factor = SCALE_FACTORS[0]  # use first entry as initial factor on boot up

# Language codes for readout, need to be installed on your system
OCR_LANG = 'eng'   # Tesseract's character recognition: eng, deu, spa, fra, ita
TTS_LANG = 'en-GB' # Pico's Text to Speech: en-GB, en-US, de-DE, es-ES, fr-FR, it-IT


# define GPIO pins for (optional) push buttons
PIN_NUMBER_SCALE =  4 # physical 7, scale button
PIN_NUMBER_COLOR = 18 # physical 12, colour mode button

# Readout uses a background process to run OCR and TTS
bg_process = None

# fbset is supported on new and legacy OS
# shows actual framebuffer resolution instead of physical screen size
def screen_resolution_fbset():
    try:
        result = subprocess.run(['fbset'], capture_output=True)
        output = result.stdout.decode('utf-8')
        #  shows resolution e.g. as 'mode "1920x1080"'
        m = re.search('mode "([0-9]+)x([0-9]+)"', output)
        if m:
            width = int(m.group(1))
            height = int(m.group(2))
            print('fbset screen resolution (w, h): ', width, height)
            return width, height
        else:
            print('Could not match fbset output:', output)
    except:
        pass
    return SCREEN_WIDTH, SCREEN_HEIGHT

def picamera2_invert(request):
    # picamera2 doesn't support image_effect, need to invert manually instead
    if hasattr(invert, 'is_inverted') and invert.is_inverted:
        with MappedArray(request, "main") as m:
            array = m.array
            for i in range(len(array)):
                array[i] = 255 - array[i]


# toggle between normal and inverted colours
def invert():
    global camera
    if hasattr(camera, 'image_effect'):
        # image_effect is not supported in picamera2
        camera.image_effect = 'none' if camera.image_effect == 'negative' else 'negative'
    else:
        # toggle state variable which is used in picamera2_invert
        if not hasattr(invert, 'is_inverted'):
            invert.is_inverted = False
        invert.is_inverted = not invert.is_inverted

# react on button pressed
def next_factor():
    global factor
        
    # find the highest entry in SCALE_FACTORS that is <= current factor
    # if the current factor is less due to direct input, switch to default value
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
# always start in top left corner to maintain the same reading position
def scale(new_factor):
    global camera
    global factor
    global screen
    
    # print("Scale factor", factor)

    # in legacy OS update roi value
    if hasattr(camera, 'crop'):
        # offset and width / height in range [0,1]
        diameter = min(1 / factor, 1)
        camera.crop = (0, 0, diameter, diameter)
        return

    # in current OS compute pixel positions in sensor based on scale factor and screen ratio
    screen_w, screen_h = screen
    screen_ratio = screen_w / screen_h
    camera_w, camera_h = camera.camera_properties['PixelArraySize']

    crop_w = int(camera_w / factor)
    crop_h = min(int(crop_w / screen_ratio), camera_h)

    window = (0, 0, crop_w, crop_h)
    camera.set_controls({'ScalerCrop': window})
    
    # focus on cropped area if camera supports autofocus
    if 'AfMode' in camera.camera_controls and DISTANCE_TO_SURFACE_CM is None:
        camera.set_controls({'AfMode': controls.AfModeEnum.Auto, 'AfMetering': controls.AfMeteringEnum.Windows})
        camera.set_controls({'AfWindows': [window]})
        camera.autofocus_cycle()

# focus on whole sensor field regardless of current preview area
def focus():
    global camera

    # update autofocus (only supported on picamera2)
    if hasattr(camera, 'camera_controls') and 'AfMode' in camera.camera_controls:
        camera.set_controls({'AfMode': controls.AfModeEnum.Auto, 'AfMetering': controls.AfMeteringEnum.Auto})
        camera.autofocus_cycle()

def quit():
    global devices    
    asyncio.get_event_loop().stop()
    for dev in devices:
        dev.ungrab()

def save_photo(filename = ''):
    global camera
    if len(filename) == 0:
        timestamp = datetime.now().isoformat()
        filename = f'/home/pi/{timestamp}.jpg'
    if hasattr(camera, 'capture_file'):
        # saves the preview stream as an image
        camera.capture_file(filename)
    else:
        camera.stop_preview()
        camera.capture(filename)
        camera.start_preview()

def readout():
    global factor
    global bg_process 
    cmd = f'tesseract tmp.jpg tmp -l {OCR_LANG} && aplay plop.wav && pico2wave -w tmp.wav -l {TTS_LANG} < tmp.txt && aplay tmp.wav'
    if bg_process != None and bg_process.poll() == None:
        # if background process is running, just kill it and do nothing
        os.killpg(os.getpgid(bg_process.pid), signal.SIGTERM)
    else:
        subprocess.call('aplay plop.wav', shell=True)
        save_photo('tmp.jpg')
        bg_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True, preexec_fn=os.setsid)

# start displaying the default camera view
def init_camera(width, height):
    try:
        # for current OS use picamera2
        picam2 = Picamera2()
        transform = Transform(hflip=1, vflip=1) if ROTATION == 180 else Transform()
        config = picam2.create_preview_configuration({'size': (width, height)}, transform=transform)
        picam2.configure(config)
        picam2.pre_callback = picamera2_invert
        picam2.start_preview(Preview.DRM, x=0, y=0, width=width, height=height) # no transform!
        picam2.start()
        if 'AfMode' in picam2.camera_controls:
            if DISTANCE_TO_SURFACE_CM is None:
                # if no distance given, use autofocus on magnification change
                picam2.set_controls({'AfMode': controls.AfModeEnum.Auto})
                picam2.set_controls({'AfSpeed': controls.AfSpeedEnum.Fast})
            else:
                # set focus to the given fixed distance
                picam2.set_controls({'AfMode': controls.AfModeEnum.Manual})
                picam2.set_controls({'LensPosition': 100 / DISTANCE_TO_SURFACE_CM})

        print('Started picamera2', ROTATION)
        return picam2
    except:
        # for legacy OS use picamera
        camera = PiCamera()
        camera.rotation = ROTATION
        camera.start_preview()
        print('Started legacy picamera', ROTATION)
        return camera


async def handle_events(device):
    async for event in device.async_read_loop():
        if event.type == evdev.ecodes.EV_KEY and event.value == 0:
            code = event.code
            # mouse buttons
            if code == evdev.ecodes.BTN_MOUSE: next_factor()
            elif code == evdev.ecodes.BTN_RIGHT: invert()
            elif code == evdev.ecodes.BTN_MIDDLE: readout()

            # regular keys
            elif code == evdev.ecodes.KEY_F: focus()
            elif code == evdev.ecodes.KEY_Q: quit()
            elif code == evdev.ecodes.KEY_ESC: quit()
            elif code == evdev.ecodes.KEY_ENTER: next_factor()
            elif code == evdev.ecodes.KEY_SLASH: invert()
            elif code == evdev.ecodes.KEY_S: save_photo()
            elif code == evdev.ecodes.KEY_R: readout()
            elif code == evdev.ecodes.KEY_0: scale(10)
            elif code == evdev.ecodes.KEY_1: scale(1)
            elif code == evdev.ecodes.KEY_2: scale(2)
            elif code == evdev.ecodes.KEY_3: scale(3)
            elif code == evdev.ecodes.KEY_4: scale(4)
            elif code == evdev.ecodes.KEY_5: scale(5)
            elif code == evdev.ecodes.KEY_6: scale(6)
            elif code == evdev.ecodes.KEY_7: scale(7)
            elif code == evdev.ecodes.KEY_8: scale(8)
            elif code == evdev.ecodes.KEY_9: scale(9)

            # numeric keypad
            elif code == evdev.ecodes.KEY_KPENTER: next_factor()
            elif code == evdev.ecodes.KEY_KPSLASH: invert()
            elif code == evdev.ecodes.KEY_KP0: scale(10)
            elif code == evdev.ecodes.KEY_KP1: scale(1)
            elif code == evdev.ecodes.KEY_KP2: scale(2)
            elif code == evdev.ecodes.KEY_KP3: scale(3)
            elif code == evdev.ecodes.KEY_KP4: scale(4)
            elif code == evdev.ecodes.KEY_KP5: scale(5)
            elif code == evdev.ecodes.KEY_KP6: scale(6)
            elif code == evdev.ecodes.KEY_KP7: scale(7)
            elif code == evdev.ecodes.KEY_KP8: scale(8)
            elif code == evdev.ecodes.KEY_KP9: scale(9)

button1 = Button(PIN_NUMBER_SCALE)
button1.when_pressed = next_factor
button2 = Button(PIN_NUMBER_COLOR)
button2.when_pressed = invert

screen = screen_resolution_fbset()
width, height = screen
camera = init_camera(width, height)
scale(factor)

try:
    devices = [evdev.InputDevice(fn) for fn in evdev.list_devices()]
    for device in devices:
        device.grab()
        asyncio.ensure_future(handle_events(device))
    loop = asyncio.get_event_loop()
    loop.run_forever()

finally:
    if bg_process != None and bg_process.poll() == None:
        os.killpg(os.getpgid(bg_process.pid), signal.SIGTERM)
    camera.stop_preview()
    camera.close()
