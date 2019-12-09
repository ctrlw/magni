# magni
Software for a simple video magnifier running on Raspberry Pi

## Description
This project aims to build a video magnifier based on Raspberry Pi and its camera. It can be used to see printed text or images at a larger scale, or to identify small parts like SMD electronics. The device has to be connected to a monitor which will display the image from the camera at a specific magnification level. The user can step through predefined scale factors with a push-button or the Enter key, and switch to colour-inversion with a second push button or the "/" key.

## Hardware
To build the magnifier, you need at least the following
* Raspberry Pi
  * any model will do (Raspberry Pi Zero is nice for its size, but needs specific cables/adapters for camera and USB)
* Raspberry Pi camera
  * Strongly recommended is an official Raspberry Pi camera v2, due to better image quality and flexible focus
* Raspberry Pi camera cable
  * only if the standard 15cm cable is too short or you need the smaller cable for Raspberry Pi Zero
* Micro USB charger
* Micro SD card (>= 4GB)
* HDMI monitor + cable
* Material for the mount

A more in-depth description of 2 hardware setups is given at http://www.fhack.org/2018/12/19/raspberry-pi-video-magnifier-2018/

If you use the optional push buttons, the script expects them at Pin 7 for the scale button and Pin 12 for the colour-switch button, using physical numbering (7 being the 4th pin on the left, 12 being the 6th pin on the right of the GPIO). Each button needs to be connected with GND, e.g. at pins 9 and 14.

## Setup
* Download [Raspbian Buster Lite](https://www.raspberrypi.org/downloads/raspbian/) and install on SD card
* Connect camera
* Login with default user “pi”, password “raspberry” (if on desktop, open a terminal)
* Run `sudo raspi-config`
  * Interfacing options -> Enable camera
  * Boot options -> Desktop / CLI -> Console Autologin
  * Network options -> Setup Wifi (unless you connect by cable)
  * Save and reboot
* After reboot, run the following commands in the terminal:
```
sudo apt-get update
sudo apt-get upgrade
sudo apt-get install python-rpi.gpio python3-rpi.gpio
wget https://github.com/ctrlw/magni/raw/master/magni.py
chmod +x magni.py
echo "clear" >> .bashrc
echo "./magni.py" >> .bashrc
```
* To hide the messages during startup, edit /boot/cmdline.txt:
`sudo nano /boot/cmdline.txt`
  * Append the following at the end of the line and save the file:
` logo.nologo quiet splash`
  * Leave nano with Ctrl-x, press “y” to save and enter to update the given file

### Support hard shut-down
This step allows to simply unplug the Raspberry Pi without possible damage to the SD card. This should be the last step, as the system will be made read-only.
```
wget https://github.com/adafruit/Raspberry-Pi-Installer-Scripts/raw/master/read-only-fs.sh
sudo bash read-only-fs.sh
```
The script asks a couple of questions:
* Continue? y
* Enable boot-time read/write jumper? N
* Install GPIO-halt utility? N
* Enable kernel panic watchdog? N
* CONTINUE? y

If you want to do changes after running the script, run the following commands:
* to enable writing again: `mount -o remount,rw /`
* to make it read-only again: `mount -o remount,ro /`

You can use them to change files like magni.py later, but they will not undo all the changes from the read-only-fs.sh script.

