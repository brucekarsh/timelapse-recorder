from PIL import Image, ImageTk
import configparser
import datetime
import numpy as np
import cv2
import os
import tkinter
from tkinter import messagebox
import time
import threading
import random
import re
import queue
import signal
import subprocess
from tkinter import ttk
import sys


class TimelapseRecorder:
  def __init__(self):
    self.frameCount = 0
    if sys.platform == 'linux':
        self.isLinux = True
    else:
        self.isLinux = False
    self.imageDisplayWidth = 640
    self.imageDisplayHeight = 480
    self.font = cv2.FONT_HERSHEY_SIMPLEX
    self.fontScale = 1
    self.fontColor = (255, 255, 255)
    self.lineThickness = 2
    self.config = configparser.ConfigParser()
    self.config.read('config.ini')
    if not 'config' in self.config:
        self.config['config'] = {}

    prefix = self.getConfigValue('config', 'filePrefix', fallback='TL_')
    outputDirectory = self.getConfigValue('config', 'outputDirectory', fallback='~/Desktop')

    self.captureWidth = 1920
    self.captureHeight = 1080
    self.fps = 5.0
    self.callbackInterval = 100
    self.running = False
    self.root = tkinter.Tk()
    self.root.title("timelapse-recorder")
    self.cap = cv2.VideoCapture()

    self.buttonFrame = tkinter.Frame(self.root)
    self.buttonFrame.pack(fill='x')
    self.configFrame = tkinter.Frame(self.root)
    self.configFrame.pack(fill='x')
    self.configFrame.pack_forget()

    self.startStopButton = ttk.Button(
            self.buttonFrame,
            text="StartStop",
            command=self.startStop)
    self.startStopButton.pack(side=tkinter.LEFT, anchor=tkinter.W, fill='x')

    im = Image.open('record-circle-fill.gif')
    self.startPhoto = ImageTk.PhotoImage(im)
    im = Image.open('stop-fill.gif')
    self.stopPhoto = ImageTk.PhotoImage(im)
    self.startStopButton.photo = (self.stopPhoto, self.startPhoto)

    self.showConfigStringVar = tkinter.StringVar()
    self.showConfigButton = ttk.Checkbutton(
            self.buttonFrame, text='configure', variable=self.showConfigStringVar,
            command=self.showConfigButtonToggle, onvalue='on', offvalue='off')
    self.showConfigButton.pack(side=tkinter.RIGHT)

    filePrefixLabel = ttk.Label(self.configFrame, text='filename prefix')
    filePrefixLabel.pack(side=tkinter.LEFT)
    self.filePrefixStringVar = tkinter.StringVar()
    self.filePrefixStringVar.set(prefix)
    self.filePrefixStringVar.trace('w', self.filePrefixChange)
    self.filePrefixEntry = ttk.Entry(
            self.configFrame, textvariable=self.filePrefixStringVar, width=4)
    self.filePrefixEntry.pack(side=tkinter.LEFT)

    outputDirectoryLabel = ttk.Label(self.configFrame, text='output directory')
    outputDirectoryLabel.pack(side=tkinter.LEFT)
    self.outputDirectoryStringVar = tkinter.StringVar()
    self.outputDirectoryStringVar.set(outputDirectory)
    self.outputDirectoryStringVar.trace('w', self.outputDirectoryChange)
    self.outputDirectoryEntry = ttk.Entry(
            self.configFrame, textvariable=self.outputDirectoryStringVar)
    self.outputDirectoryEntry.pack(side=tkinter.LEFT)

    cameraPortLabel = ttk.Label(self.configFrame, text='camera port')
    cameraPortLabel.pack(side=tkinter.LEFT)

    self.cameraPortStringVar = tkinter.StringVar()
    self.cameraPortStringVar.trace('w', self.cameraPortChange)
    if (not self.isLinux):
      self.cameraPortStringVar.set(str(self.getCameraPortNumber()))
      self.cameraPortEntry = ttk.Entry(self.configFrame, textvariable=self.cameraPortStringVar)
      self.cameraPortEntry.pack(side=tkinter.LEFT)
    else:
      v4lportNumbers, v4ldescriptions = self.enumerateVideoPorts()
      choices = []
      for i in range(len(v4lportNumbers)):
          choices.append(str(v4lportNumbers[i]) + " " + v4ldescriptions[i])
      if (self.getCameraPortString() in choices):
        self.cameraPortStringVar.set(self.getCameraPortString())
      else:
        self.cameraPortStringVar.set(choices[0])
      self.cameraPortOptionMenu = tkinter.OptionMenu(
              self.configFrame, self.cameraPortStringVar, *choices)
      self.cameraPortOptionMenu.pack()

    self.imageLabel = ttk.Label(self.root)
    self.imageLabel.pack(fill='both', expand=1)

    self.frame_pil = ImageTk.PhotoImage(Image.fromarray(np.zeros(
        (self.imageDisplayHeight, self.imageDisplayWidth) ) ))
    self.imageLabel.configure(image=self.frame_pil)

    self.statusLabel = ttk.Label(self.root)
    self.statusLabel.pack(side=tkinter.BOTTOM, fill='x')


    signal.signal(signal.SIGINT, self.signal_handler)
    self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    self.out = None
    self.makeStartStopButtonAStartButton()
    #self.root.resizable(0, 0)
    self.root.mainloop()

  def annotateFrame(self, frame):
      text = str(self.now())
      textSize, textBaseline = cv2.getTextSize(text, self.font, self.fontScale, self.lineThickness)
      textXSize = textSize[0]
      textYSize = textSize[1]
      frameXSize = frame.shape[1]
      frameYSize = frame.shape[0]
      pos = (4, frameYSize - 4)
      cv2.putText(
              frame,
              text,
              pos,
              self.font,
              self.fontScale,
              self.fontColor,
              self.lineThickness)

  def callback(self):
    self.updateStatusMessage()
    if not self.running:
      return  # just return if we get a leftover callback
    self.root.after(self.callbackInterval, self.callback)
    ret, frame = self.cap.read()
    if ret == True:
      self.annotateFrame(frame)

      self.enqueue_for_display(self.now(), frame)
      self.frameCount += 1
    else:
      self.fail()

  def cameraPortChange(self, *args):
    text = self.cameraPortStringVar.get()
    if self.validateCameraPortChange(text):
      self.setConfigValue('config', 'cameraPort', text)

  def enqueue_for_display(self, t, frame):
    self.out.write(frame)
    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    imageDisplayWidth = self.imageLabel.winfo_width() - 2
    imageDisplayHeight = self.imageLabel.winfo_height() - 2

    image = Image.fromarray(frame).resize( (imageDisplayWidth, imageDisplayHeight), Image.ANTIALIAS)
    self.frame_pil = ImageTk.PhotoImage(image)
    self.imageLabel.imagedata = self.frame_pil
    self.imageLabel.configure(image=self.frame_pil)
    self.root.update_idletasks()

  def enumerateVideoPorts(self):
  #   This works for Linux but probably not for anything else.
      v4lnames = subprocess.check_output("ls /sys/class/video4linux/", shell=True).decode(
             "utf8").strip().split('\n')
      v4ldescriptions = subprocess.check_output(
              "cat /sys/class/video4linux/*/name", shell=True).decode("utf8").strip().split('\n')
      v4lportNumbers = [int(x[5:]) for x in v4lnames]
      return (v4lportNumbers, v4ldescriptions)
    
  def fail(self):
    self.stop()
    cameraPort = self.getConfigValue('config', 'cameraPort', '0')
    messagebox.showerror("Video read failed.", "Video read failed. Stopping." +
            "\nCamera port is " + cameraPort)

  def filePrefixChange(self, *args):
    text = self.filePrefixEntry.get()
    if self.validateFilePrefixChange(text):
      self.setConfigValue('config', 'filePrefix', text)

  def getCameraPortString(self):
    return self.getConfigValue('config', 'cameraPort', fallback='0')

  def getCameraPortNumber(self):
    return int(self.getCameraPortString().split(" ")[0])

  def getConfigValue(self, section, key, fallback):
    # look up the value
    value = self.config.get(section, key, fallback=fallback)
    # write it back in case it was a default value
    self.setConfigValue(section, key, value)
    return value

  def getPortNumberFromChoice(self, choice):
    return int(choice.split(" ")[0])

  def getStatusMessage(self):
      string1 = "Running." if self.running else "Stopped."
      return string1 + " " + str(self.frameCount) + " frames recorded"

  def makeFilename(self):
    prefix = self.filePrefixEntry.get()
    outputDirectory = self.outputDirectoryEntry.get()
    date = self.now().strftime("%Y%m%d-%H%M%S")
    filename = os.path.expanduser(os.path.join(outputDirectory, prefix + date + '.mov'))
    # TODO: validate path.
    # TODO: check for pre-existing file. Wait and retry if present.
    # TODO: check for disk space
    return filename

  def makeStartStopButtonAStartButton(self):
      self.startStopButton.configure(
          image=self.startPhoto, text='record', compound=tkinter.LEFT)

  def makeStartStopButtonAStopButton(self):
      self.startStopButton.configure(
          image=self.stopPhoto, text='stop', compound=tkinter.LEFT)
      
  def now(self):
    return datetime.datetime.now()

  def on_closing(self):
    if messagebox.askokcancel("Quit", "Do you want to quit?"):
      self.shutdown()

  def outputDirectoryChange(self, *args):
    text = self.outputDirectoryEntry.get()
    if self.validateOutputDirectoryChange(text):
      self.setConfigValue('config', 'outputDirectory', text)

  def setAutofocus(self, b):
    # This only works on linux
    if not self.isLinux:
      return
    if b:
      subprocess.check_output(
          "v4l2-ctl -d /dev/video1 --set-ctrl=focus_auto=1", shell=True).decode(
           "utf8").strip().split('\n')
    else:
      subprocess.check_output(
          "v4l2-ctl -d /dev/video1 --set-ctrl=focus_auto=0", shell=True).decode(
           "utf8").strip().split('\n')

  def setConfigValue(self, section, key, value):
    self.config[section][key] = value;
    self.writebackConfig()

  def showConfigButtonToggle(self, *args):
      if self.showConfigStringVar.get() == 'on':
        self.buttonFrame.pack_forget()
        self.imageLabel.pack_forget()
        self.statusLabel.pack_forget()

        self.buttonFrame.pack(fill='x')
        self.configFrame.pack(fill='x')
        self.statusLabel.pack(side=tkinter.BOTTOM, fill='x')
        self.imageLabel.pack(fill='both', expand=1)
      else:
        self.configFrame.pack_forget()

  def shutdown(self):
    self.cap.release()
    if self.out:
      self.out.release()
    cv2.destroyAllWindows()
    sys.exit(0)

  def signal_handler(self, sig, frame):
    self.shutdown()

  def start(self):
    self.cap.open(self.getCameraPortNumber())
    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(self.captureWidth))
    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self.captureHeight))
    self.cap.set(cv2.CAP_PROP_FPS, self.fps)
    self.setAutofocus(True)
    self.frameCount = 0
    filename = self.makeFilename()
    self.makeStartStopButtonAStopButton()
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    self.out = cv2.VideoWriter(filename, fourcc, self.fps, (self.captureWidth, self.captureHeight))
    self.updateStatusMessage()


    if self.out.isOpened():
      self.running = True
      self.root.after(self.callbackInterval, self.callback)
    else:
        messagebox.showerror("output file open failed", "could not open " + filename)
        self.stop()

  def startStop(self):
    if self.running:
      self.stop()
    else:
      self.start()
  
  def stop(self):
    self.makeStartStopButtonAStartButton()
    if self.out:
      self.out.release()
      self.out = None
    self.running = False
    self.updateStatusMessage()

  def updateStatusMessage(self):
    statusMessage = self.getStatusMessage()
    self.statusLabel.configure(text=statusMessage)

  def validateCameraPortChange(self, text):
      # TODO WRITEME
      return True

  def validateFilePrefixChange(self, text):
      # TODO WRITEME
      return True

  def validateOutputDirectoryChange(self, text):
      # TODO WRITEME
      return True

  def writebackConfig(self):
    with open('config.ini', 'w') as configfile:
      self.config.write(configfile)


def main():
    TimelapseRecorder()

main()
