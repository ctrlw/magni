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

# numpy and cv2 are only needed for the overlay text
try:
    import cv2
    print("Using cv2")
    import numpy as np
    print("Using numpy")
except ImportError:
    pass

import os                      # for background OCR and TTS process
import re                      # for parsing fbset output
import signal                  # to kill background process 
import subprocess              # for calling fbset to detect screen resolution and readout
import sys                     # for checking if modules are loaded

# You can adapt this script to your specific setup, by changing the constants 
# SCALE_FACTORS can be modified for a fixed set of scale factors
# PIN_NUMBER_... can be changed if you connect buttons to different GPIO pins

# Picamera2 needs the screen resolution for preview
# Default is full HD, will try to read actual values in init_camera
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080

# Rotate view by 180 degrees for the typical use-case with camera behind object
ROTATION = 180

# Increase contrast to make text more readable
# 1 is default, bigger numbers increase contrast
CONTRAST = 1

# Increase brightness for more clarity, 0 is default, range -1..1
BRIGHTNESS = 0.2

# Increase saturation for stronger colours, 1 is default, range 0..32
SATURATION = 1

# Increase sharpness, 1 is default, range 0..16
SHARPNESS = 1

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

AUDIO = 'aplay'
# uncomment next line to get audio via HDMI, see https://forums.raspberrypi.com/viewtopic.php?t=351718
# AUDIO = 'aplay -D sysdefault:CARD=vc4hdmi'

# define GPIO pins for (optional) push buttons
PIN_NUMBER_SCALE =  4 # physical 7, scale button
PIN_NUMBER_COLOR = 18 # physical 12, colour mode button

# Enable overlay text for debugging
ENABLE_OVERLAY = False

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

# show text on screen
def overlay(text):
    global camera

    if ENABLE_OVERLAY and 'numpy' in sys.modules and 'cv2' in sys.modules:
        colour = (255, 0, 0, 255)
        origin = (0, 50)
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 1
        thickness = 2
        buffer = np.zeros((200, 400, 4), dtype=np.uint8)
        cv2.putText(buffer, text, origin, font, scale, colour, thickness)
        camera.set_overlay(buffer)

def picamera2_invert(request):
    # picamera2 doesn't support image_effect, need to invert manually instead
    if hasattr(invert, 'is_inverted') and invert.is_inverted:
        with MappedArray(request, "main") as m:
            array = m.array
            for i in range(len(array)):
                array[i] = ~array[i]


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
    
    # ensure that factor is at least 1
    factor = max(1, new_factor)

    # in legacy OS update roi value
    if hasattr(camera, 'crop'):
        # offset and width / height in range [0,1]
        diameter = min(1 / factor, 1)
        camera.crop = (0, 0, diameter, diameter)
        return

    # in current OS compute pixel positions in sensor based on scale factor and screen ratio
    screen_w, screen_h = screen
    screen_ratio = screen_w / screen_h
    x, y, camera_w, camera_h = camera.camera_properties['ScalerCropMaximum']

    crop_w = int(camera_w / factor)
    crop_h = min(int(crop_w / screen_ratio), camera_h)

    window = (x, y, crop_w, crop_h)
    camera.set_controls({'ScalerCrop': window})
    overlay(f'{factor:.2f}')
    
    # focus on cropped area if camera supports autofocus
    if 'AfMode' in camera.camera_controls and DISTANCE_TO_SURFACE_CM is None:
        camera.set_controls({'AfMode': controls.AfModeEnum.Auto, 'AfMetering': controls.AfMeteringEnum.Windows})
        camera.set_controls({'AfWindows': [window]})
        camera.autofocus_cycle()

# change scale factor by given amount
def zoom(change_by):
    global factor
    scale(factor + change_by)

# change brightness by given amount
def brightness(change_by):
    global camera

    if hasattr(camera, 'camera_controls') and 'Brightness' in camera.camera_controls:
        min_val, max_val, def_val = camera.camera_controls['Brightness']
        if not hasattr(brightness, 'val'):
            # init static var with default brightness value
            brightness.val = BRIGHTNESS
        val = brightness.val + change_by
        if min_val <= val <= max_val:
            brightness.val = val
            camera.set_controls({'Brightness': val})
            overlay(f'{val:.2f}')


# multiply current contrast by given value
def contrast(multiply_by):
    global camera

    if hasattr(camera, 'camera_controls') and 'Contrast' in camera.camera_controls:
        min_contrast, max_contrast, def_contrast = camera.camera_controls['Contrast']
        if not hasattr(contrast, 'contrast'):
            # init static var with default contrast value (1)
            contrast.contrast = CONTRAST
        val = contrast.contrast * multiply_by
        if min_contrast <= val <= max_contrast:
            contrast.contrast = val
            camera.set_controls({'Contrast': val})
            overlay(f'{val:.2f}')
    elif hasattr(camera, 'contrast'):
        # legacy picamera, uses range from -100 to 100 so just stepping +-10
        diff = 10 if multiply_by > 1 else -10
        val = camera.contrast + diff
        if -100 <= val <= 100:
            camera.contrast = val

# multiply current saturation by given value
def saturation(multiply_by):
    global camera
    if hasattr(camera, 'camera_controls') and 'Saturation' in camera.camera_controls:
        min_val, max_val, def_val = camera.camera_controls['Saturation']
        if not hasattr(saturation, 'val'):
            # init static var with default value
            saturation.val = SATURATION
        val = saturation.val * multiply_by
        if min_val <= val <= max_val:
            saturation.val = val
            camera.set_controls({'Saturation': val})
            overlay(f'{val:.2f}')

# multiply current sharpness by given value
def sharpness(multiply_by):
    global camera
    if hasattr(camera, 'camera_controls') and 'Sharpness' in camera.camera_controls:
        min_val, max_val, def_val = camera.camera_controls['Sharpness']
        if not hasattr(sharpness, 'val'):
            # init static var with default value
            sharpness.val = SHARPNESS
        val = sharpness.val * multiply_by
        if min_val <= val <= max_val:
            sharpness.val = val
            camera.set_controls({'Sharpness': val})
            overlay(f'{val:.2f}')

# change focus (only on supported cameras like the v3 camera, using picamera2)
# multiply current LensPosition (in dioptrien, i.e. 1/distance_m) by given factor
# if None given, autofocus on whole sensor field regardless of current preview
def focus(multiply_by = None):
    global camera

    # update autofocus (only supported on picamera2)
    if hasattr(camera, 'camera_controls') and 'AfMode' in camera.camera_controls:
        current_val = camera.capture_metadata()['LensPosition']
        if multiply_by is None:
            overlay(f'Auto: {current_val:.2f}')
            camera.set_controls({'AfMode': controls.AfModeEnum.Auto, 'AfMetering': controls.AfMeteringEnum.Auto})
            camera.autofocus_cycle()
            current_val = camera.capture_metadata()['LensPosition']
            overlay(f'Auto: {current_val:.2f}')
        else:
            camera.set_controls({'AfMode': controls.AfModeEnum.Manual})
            val = current_val * multiply_by
            camera.set_controls({'LensPosition': val})
            overlay(f'{val:.2f}')

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

    # remove hyphens at end of line and append the next line, so TTS won't read them out
    # See https://unix.stackexchange.com/a/26289
    FIX_HYPHENS = "perl -i.original -p0e 's/(\w)-[\n]+(\w)/$1$2/igs' tmp.txt"

    # command to run OCR, remove hyphens, play a sound, run TTS and play the result
    cmd = f'tesseract tmp.jpg tmp -l {OCR_LANG} && {FIX_HYPHENS} && {AUDIO} plop.wav && pico2wave -w tmp.wav -l {TTS_LANG} < tmp.txt && {AUDIO} tmp.wav'
    overlay('')
    if bg_process != None and bg_process.poll() == None:
        # if background process is running, just kill it and do nothing
        os.killpg(os.getpgid(bg_process.pid), signal.SIGTERM)
    else:
        subprocess.call(f'{AUDIO} plop.wav', shell=True)
        save_photo('tmp.jpg')
        overlay('Reading')
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
        picam2.set_controls({
            'Brightness': BRIGHTNESS,
            'Contrast': CONTRAST,
            'Saturation': SATURATION,
            'Sharpness': SHARPNESS
        })
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
            modifiers = device.active_keys()
            is_shift = evdev.ecodes.KEY_LEFTSHIFT in modifiers or evdev.ecodes.KEY_RIGHTSHIFT in modifiers

            # mouse buttons
            if code == evdev.ecodes.BTN_MOUSE: next_factor()
            elif code == evdev.ecodes.BTN_RIGHT: invert()
            elif code == evdev.ecodes.BTN_MIDDLE: readout()

            # regular keys
            elif code == evdev.ecodes.KEY_A: focus()
            elif code == evdev.ecodes.KEY_F and is_shift: focus(0.75)
            elif code == evdev.ecodes.KEY_F: focus(1.5)
            elif code == evdev.ecodes.KEY_Q: quit()
            elif code == evdev.ecodes.KEY_ESC: quit()
            elif code == evdev.ecodes.KEY_ENTER: next_factor()
            elif code == evdev.ecodes.KEY_SLASH: invert()
            elif code == evdev.ecodes.KEY_S: save_photo()
            elif code == evdev.ecodes.KEY_R: readout()
            elif code == evdev.ecodes.KEY_Z and is_shift: zoom(-0.2)
            elif code == evdev.ecodes.KEY_Z: zoom(0.2)
            elif code == evdev.ecodes.KEY_B and is_shift: brightness(-0.1)
            elif code == evdev.ecodes.KEY_B: brightness(0.1)
            elif code == evdev.ecodes.KEY_C and is_shift: contrast(0.5)
            elif code == evdev.ecodes.KEY_C: contrast(2)
            elif code == evdev.ecodes.KEY_H and is_shift: sharpness(0.5)
            elif code == evdev.ecodes.KEY_H: sharpness(2)
            elif code == evdev.ecodes.KEY_T and is_shift: saturation(0.5)
            elif code == evdev.ecodes.KEY_T: saturation(2)
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
