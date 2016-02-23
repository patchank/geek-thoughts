import StringIO
import subprocess
import sys
import os
import signal
import time
from datetime import datetime
from PIL import Image
import requests
from requests.auth import HTTPBasicAuth
import RPi.GPIO as GPIO
import ibmiotf.device

url = 'https://gateway.watsonplatform.net/visual-recognition-beta/api/v2/classify?version=2015-12-02'
GPIO.setmode(GPIO.BCM)
GPIO.setup(21,GPIO.IN)

options = {
    "org": "vcj3bj",
    "type": "bike",
    "id": "dos",
    "auth-method": "token",
    "auth-token": "N7-4CBaCzUPO9LDaLJ"
}

client = ibmiotf.device.Client(options)
client.connect()
myData={'kind':'cleo'}

# Motion detection settings:
# Threshold (how much a pixel has to change by to be marked as "changed")
# Sensitivity (how many changed pixels before capturing an image)
# ForceCapture (whether to force an image to be captured every forceCaptureTime seconds)
threshold = 10
sensitivity = 50
forceCapture = True
forceCaptureTime = 60 * 60 # Once an hour

# File settings
saveWidth = 1280
saveHeight = 960
diskSpaceToReserve = 40 * 1024 * 1024 # Keep 40 mb free on disk

# Capture a small test image (for motion detection)
def captureTestImage():
    command = "raspistill -w %s -h %s -t 200 -e bmp -o -" % (100, 75)
    sys.stdout.write('.')
    sys.stdout.flush()
    imageData = StringIO.StringIO()
    imageData.write(subprocess.check_output(command, shell=True))
    imageData.seek(0)
    im = Image.open(imageData)
    buffer = im.load()
    imageData.close()
    return im, buffer

# Save a full size image to disk
def saveImage(width, height, diskSpaceToReserve):
    keepDiskSpaceFree(diskSpaceToReserve)
    nowTime = datetime.now()
    filename = "captures/capture-%04d%02d%02d-%02d%02d%02d.jpg" % (nowTime.year, nowTime.month, nowTime.day, nowTime.hour, nowTime.minute, nowTime.second)
    subprocess.call("raspistill -w 1296 -h 972 -t 200 -e jpg -q 15 -vf -hf -o %s" % filename, shell=True)
    print
    print "Captured %s" % filename
    #check content
    files = {'images_file': open(filename, 'rb')}
    response = requests.post(url, auth=HTTPBasicAuth('48b25a3f-07fc-48c5-a302-abfc4d07a299','hbZAAbc2igV5'), files=files)
    r = response.json()

    for x in r['images'][0]['scores']:
        if(x['name']=='cleo' and x['score']>0.6):
            print 'It''s a Cleo ' + str(x['score'])
            client.publishEvent(event="animal", msgFormat="json", data=myData)

            proc = subprocess.Popen('./ustream', stdout=subprocess.PIPE, shell=True, preexec_fn=os.setsid)
            time.sleep(30)
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            break


# Keep free space above given level
def keepDiskSpaceFree(bytesToReserve):
    if (getFreeSpace() < bytesToReserve):
        for filename in sorted(os.listdir(".")):
            if filename.startswith("capture") and filename.endswith(".jpg"):
                os.remove(filename)
                print "Deleted %s to avoid filling disk" % filename
                if (getFreeSpace() > bytesToReserve):
                    return

# Get available disk space
def getFreeSpace():
    st = os.statvfs(".")
    du = st.f_bavail * st.f_frsize
    return du
        
# Get first image
image1, buffer1 = captureTestImage()

# Reset last capture time
lastCapture = time.time()

while (True):
    # Get comparison image
    image2, buffer2 = captureTestImage()

    # Count changed pixels
    changedPixels = 0
    for x in xrange(0, 100):
        for y in xrange(0, 75):
            # Just check green channel as it's the highest quality channel
            pixdiff = abs(buffer1[x,y][1] - buffer2[x,y][1])
            if pixdiff > threshold:
                changedPixels += 1

    # Check force capture
    if forceCapture:
        if time.time() - lastCapture > forceCaptureTime:
            changedPixels = sensitivity + 1
                
    # Save an image if pixels changed
    if changedPixels > sensitivity:
        lastCapture = time.time()
        saveImage(saveWidth, saveHeight, diskSpaceToReserve)
    
    # Swap comparison buffers
    image1 = image2
    buffer1 = buffer2