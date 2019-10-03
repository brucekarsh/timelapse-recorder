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
import queue
import signal
from tkinter import ttk
import sys

class TimelapseRecorder:
  def makeFilename(self):
    prefix = self.filePrefixEntry.get()
    outputDirectory = self.outputDirectoryEntry.get()
    date = self.now().strftime("%Y%m%d-%H%M%S")
    filename = os.path.expanduser(os.path.join(outputDirectory, prefix + date + '.avi'))
    # TODO: validate path.
    # TODO: check for pre-existing file. Wait and retry if present.
    # TODO: check for disk space
    return filename

  def __init__(self):
    self.frameCount = 0
    self.config = configparser.ConfigParser()
    self.config.read('config.ini')
    if not 'config' in self.config:
        self.config['config'] = {}
    prefix = self.config.get('config', 'filePrefix', fallback='TL_')
    self.config['config']['filePrefix'] = prefix
    outputDirectory = self.config.get('config', 'outputDirectory', fallback='~/Desktop')
    self.config['config']['outputDirectory'] = outputDirectory
    self.width = 640
    self.height = 480
    self.callbackInterval = 100
    self.running = False
    self.root = tkinter.Tk(  )
    self.cap = cv2.VideoCapture(0)

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
    self.filePrefixEntry = ttk.Entry(self.configFrame, textvariable=self.filePrefixStringVar, width=4)
    self.filePrefixEntry.pack(side=tkinter.LEFT)

    outputDirectoryLabel = ttk.Label(self.configFrame, text='output directory')
    outputDirectoryLabel.pack(side=tkinter.LEFT)
    self.outputDirectoryStringVar = tkinter.StringVar()
    self.outputDirectoryStringVar.set(outputDirectory)
    self.outputDirectoryStringVar.trace('w', self.outputDirectoryChange)
    self.outputDirectoryEntry = ttk.Entry(self.configFrame, textvariable=self.outputDirectoryStringVar)
    self.outputDirectoryEntry.pack(side=tkinter.LEFT)

    self.imageLabel = ttk.Label(self.root)
    self.imageLabel.pack()

    frame_pil = ImageTk.PhotoImage(Image.fromarray(np.zeros( (480, 640) ) ))
    self.imageLabel.configure(image=frame_pil)

    self.statusLabel = ttk.Label(self.root)
    self.statusLabel.pack()

    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
    self.cap.set(cv2.CAP_PROP_FPS, 5.0)

    signal.signal(signal.SIGINT, self.signal_handler)
    self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    self.writebackConfig()
    self.out = None
    self.makeStartStopButtonAStartButton()
    self.root.mainloop()

  def callback(self):
    self.updateStatusMessage()
    if not self.running:
      return  # just return if we get a leftover callback
    self.root.after(self.callbackInterval, self.callback)
    ret, frame = self.cap.read()
    if ret == True:
      self.enqueue_for_display(self.now(), frame)
      self.frameCount += 1
    else:
      self.fail()

  def enqueue_for_display(self, t, frame):
    global frame_pil
    self.out.write(frame)
    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    frame_pil = ImageTk.PhotoImage(Image.fromarray(frame))
    self.imageLabel.configure(image=frame_pil)
    self.imageLabel.image = frame_pil

  def fail(self):
    self.stop()
    messagebox.showerror("Write failed. Stopping")

  def filePrefixChange(self, *args):
    text = self.filePrefixEntry.get()
    if self.validateFilePrefixChange(text):
      self.config['config']['filePrefix'] = text
      self.writebackConfig()

  def getStatusMessage(self):
      string1 = "Running." if self.running else "Stopped."
      return string1 + " " + str(self.frameCount) + " frames recorded"

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
    if self.validateoutputDirectoryChange(text):
      self.config['config']['outputDirectory'] = text
      self.writebackConfig()

  def showConfigButtonToggle(self, *args):
      if self.showConfigStringVar.get() == 'on':
        self.buttonFrame.pack_forget()
        self.imageLabel.pack_forget
        self.statusLabel.pack_forget

        self.buttonFrame.pack(fill='x')
        self.configFrame.pack(fill='x')
        self.imageLabel.pack(side=tkinter.BOTTOM)
        self.imageLabel.pack()
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
    self.frameCount = 0
    filename = self.makeFilename()
    self.makeStartStopButtonAStopButton()
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    self.out = cv2.VideoWriter(filename, fourcc, 30.0, (self.width, self.height))
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
    print (statusMessage)
    self.statusLabel.configure(text=statusMessage)

  def validateFilePrefixChange(self, text):
      # TODO WRITEM
      return True

  def validateoutputDirectoryChange(self, text):
      # TODO WRITEM
      return True

  def writebackConfig(self):
    with open('config.ini', 'w') as configfile:
      self.config.write(configfile)


def main():
    TimelapseRecorder()

main()
