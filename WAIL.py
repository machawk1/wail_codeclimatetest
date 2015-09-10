#!/usr/bin/env python
#-*- coding:utf-8 -*-

# Web Archiving Integration Layer (WAIL)
#  This tool ties together web archiving applications including Wayback,
#   Heritrix, and Tomcat.
#  Mat Kelly <wail@matkelly.com> 2013

import wx
import subprocess
import shlex
import webbrowser
import os
import time
import sys
import datetime
import urllib
import urllib2
import base64
import glob
import re
import ssl
import shutil
import errno
from urlparse import urlparse

# from wx import *
import waybackConfigWriter
from subprocess import Popen, PIPE

# For a more asynchronous UI, esp with accessible()s
from multiprocessing import Pool as Thread
import logging
import requests
import threading  # Necessary for polling/indexing
import thread  # For a more responsive UI
from requests.auth import HTTPDigestAuth

import wxversion

import tarfile  # For updater

ssl._create_default_https_context = ssl._create_unverified_context

#  from pync import Notifier # OS X notifications

WAIL_VERSION = "1.0"

###############################
# Platform independent Messages
###############################
msg_stoppingTomcat = "Stopping Tomcat..."
msg_startingTomcat = "Starting Tomcat..."
msg_waybackEnabled = "Currently Enabled"
msg_waybackDisabled = "Currently Disabled"
msg_waybackNotStarted_title = "Wayback does not appear to be running."
msg_waybackNotStarted_body = "Launch Wayback and re-check?"
msg_uriNotInArchives = "The URL is not yet in the archives."
msg_uriInArchives_title = "This page has been archived!"
msg_uriInArchives_body = ("This URL is currently in the archives!"
                          " Hit the \"View Archive\" Button")
msg_wrongLocation_body = "WAIL must reside in your Applications directory. Move it there then relaunch.\n\nCurrent Location: "
msg_wrongLocation_title = "Wrong Location"
msg_noJavaRuntime = "No Java runtime present, requesting install."

tabLabel_basic = "Basic"
tabLabel_advanced = "Advanced"

tabLabel_advanced_general = "General"
tabLabel_advanced_wayback = "Wayback"
tabLabel_advanced_heritrix = "Heritrix"
tabLabel_advanced_miscellaneous = "Miscellaneous"
tabLabel_advanced_general_serviceStatus = "SERVICE STATUS"

serviceEnabledLabel_YES = "OK"
serviceEnabledLabel_NO = "X"

# Basic Tab Buttons
buttonLabel_archiveNow = "Archive Now!"
buttonLabel_archiveNow_initializing = "INITIALIZING"
buttonLabel_checkStatus = "Check Archived Status"
buttonLabel_viewArchive = "View Archive"
buttonLabel_uri = "URL:"
buttonLabel_fix = "Fix"
buttonLabel_kill = "Kill"

textLabel_defaultURI = "http://matkelly.com/wail"
textLabel_defaultURI_title = "WAIL homepage"

aboutWindow_appName = "Web Archiving Integration Layer (WAIL)"
aboutWindow_author = "By Mat Kelly <wail@matkelly.com>"
aboutWindow_iconPath = "/build/icons/whale.ico"
aboutWindow_iconWidth = 128
aboutWindow_iconHeight = 128

# Advanced Tab Buttons
buttonLabel_wayback = "View Wayback in Browser"
buttonLabel_wayback_launching = "Launching Wayback..."
buttonLabel_editWaybackConfig = "Edit Wayback Configuration"
buttonLabel_resetWaybackConfig = "Reset Wayback Configuration"
buttonLabel_startHeritrix = "Start Heritrix Process"
buttonLabel_viewHeritrix = "View Heritrix in Browser"
buttonLabel_setupCrawl = "Setup One-Off Crawl"
buttonLabel_viewArchiveFiles = "View Archive Files"
buttonLabel_heritrix_launchWebUI = "Launch WebUI"
buttonLabel_heritrix_launchWebUI_launching = "Launching..."
buttonLabel_heritrix_newCrawl = "New Crawl"

groupLabel_window = "Web Archiving Integration Layer"

menuTitle_about = "&About WAIL"
menuTitle_help = "&Help"
menu_destroyJob = "Destroy Job (Does not delete archive)"
menu_forceCrawlFinish = "Force crawl to finish"

heritrixCredentials_username = "lorem"
heritrixCredentials_password = "ipsum"


uri_tomcat = "http://localhost:8080/"
uri_wayback = "http://localhost:8080/wayback/"
uri_wayback_allMementos = uri_wayback + "*/"
uri_heritrix = "https://" + heritrixCredentials_username + ":" + heritrixCredentials_password + "@localhost:8443"
uri_heritrix_accessiblityURI = "https://" + heritrixCredentials_username + ":" + heritrixCredentials_password + "@localhost:8443"
uri_heritrixJob = uri_heritrix + "/engine/job/"

###############################
# Platform-specific paths
###############################

heritrixPath = ""
heritrixBinPath = ""
heritrixJobPath = ""
warcsFolder = ""
tomcatPath = ""
tomcatPathStart = ""
tomcatPathStop = ""
wailPath = os.path.dirname(os.path.realpath(__file__))
fontSize = 8
wailWindowSize = (400,250)

if 'darwin' in sys.platform:  # OS X Specific Code here
    # This should be dynamic but doesn't work with WAIL binary
    wailPath = "/Applications/WAIL.app"
    heritrixPath = wailPath + "/bundledApps/heritrix-3.2.0/"
    heritrixBinPath = "sh " + heritrixPath+"bin/heritrix"
    heritrixJobPath = heritrixPath+"jobs/"
    fontSize = 10
    tomcatPath = wailPath + "/bundledApps/tomcat"
    warcsFolder = tomcatPath + "/webapps/ROOT/files1"
    tomcatPathStart = tomcatPath + "/bin/startup.sh"
    tomcatPathStop = tomcatPath + "/bin/shutdown.sh"

    aboutWindow_iconPath = wailPath + aboutWindow_iconPath

    # Fix tomcat control scripts' permissions
    os.chmod(tomcatPathStart, 0744)
    os.chmod(tomcatPathStop, 0744)
    os.chmod(tomcatPath + "/bin/catalina.sh", 0744)
    # TODO, variable encode paths, ^ needed for startup.sh to execute

    # Change all permissions within the app bundle (a big hammer)
    for r, d, f in os.walk(wailPath):
        os.chmod(r, 0777)
elif sys.platform.startswith('linux'):
    '''Linux Specific Code here'''
elif sys.platform.startswith('win32'):
    # Win Specific Code here, this applies to both 32 and 64 bit
    # Consider using http://code.google.com/p/platinfo/ in the future for finer refinement

    aboutWindow_iconPath = wailPath + aboutWindow_iconPath

    heritrixPath = "C:/WAIL/bundledApps/heritrix-3.2.0/"
    heritrixBinPath = heritrixPath+"bin/heritrix.cmd"
    heritrixJobPath = "C:\\WAIL\\jobs\\"
    tomcatPath = "C:/WAIL/bundledApps/tomcat"
    warcsFolder = tomcatPath + "/webapps/ROOT/files1"
    tomcatPathStart = "C:/WAIL/support/catalina_start.bat"
    tomcatPathStop = "C:/WAIL/support/catalina_stop.bat"
###############################
# Tab Controller (Notebook)
###############################


class TabController(wx.Frame):
    def __init__(self):
        wx.Frame.__init__(self, None, title=groupLabel_window, size=wailWindowSize)
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        self.Notebook = wx.Notebook(panel)
        vbox.Add(self.Notebook, 2, flag=wx.EXPAND)

        panel.SetSizer(vbox)

        # Add basic config page/tab
        self.basicConfig = WAILGUIFrame_Basic(self.Notebook)
        self.Notebook.AddPage(self.basicConfig, tabLabel_basic)

        # Add advanced config page/tab
        self.advConfig = WAILGUIFrame_Advanced(self.Notebook)
        self.Notebook.AddPage(self.advConfig, tabLabel_advanced)
        self.createMenu()

    def createMenu(self):
        self.menu_bar = wx.MenuBar()
        self.help_menu = wx.Menu()

        self.help_menu.Append(wx.ID_ABOUT,   menuTitle_about)
        self.help_menu.Append(wx.ID_EXIT,   "&QUIT")
        self.menu_bar.Append(self.help_menu, menuTitle_help)

        self.Bind(wx.EVT_MENU, self.displayAboutMenu, id=wx.ID_ABOUT)
        self.Bind(wx.EVT_MENU, self.quit, id=wx.ID_EXIT)
        self.SetMenuBar(self.menu_bar)

    def displayAboutMenu(self, button):
        info = wx.AboutDialogInfo()
        info.Name = aboutWindow_appName
        info.Version = "v. " + WAIL_VERSION
        info.Copyright = aboutWindow_author
        # info.Description = "foo"
        info.WebSite = (textLabel_defaultURI, textLabel_defaultURI_title)
        # info.Developers = ["Mat Kelly"]
        # info.License = "lic info"
        info.SetIcon(wx.Icon(aboutWindow_iconPath, wx.BITMAP_TYPE_ICO, aboutWindow_iconWidth, aboutWindow_iconHeight))
        wx.AboutBox(info)

    def ensureCorrectInstallation(self):
        # TODO: properly implement this
        # Check that the file is being executed from the correct location
        if 'darwin' in sys.platform and os.path.dirname(os.path.abspath(__file__)) != "/Applications":
            # Alert the user to move the file. Exit the program
            wx.MessageBox(msg_wrongLocation_body + os.path.dirname(os.path.abspath(__file__)), msg_wrongLocation_title,)
            print msg_wrongLocation_body + os.path.dirname(os.path.abspath(__file__))
            #sys.exit()

    def quit(self, button):
        sys.exit()


class WAILGUIFrame_Basic(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        self.uriLabel = wx.StaticText(self, -1, buttonLabel_uri, pos=(0, 5))
        self.uri = wx.TextCtrl(self, -1, pos=(30, 0), value=textLabel_defaultURI, size=(350, 25))
        self.archiveNowButton = wx.Button(self, -1, buttonLabel_archiveNow, pos=(0, 30))
        self.checkArchiveStatus = wx.Button(self,  -1, buttonLabel_checkStatus, pos=(105, 30))
        self.viewArchive = wx.Button(self, -1, buttonLabel_viewArchive, pos=(270, 30))

        self.archiveNowButton.SetDefault()

        # Basic interface button actions
        self.archiveNowButton.Bind(wx.EVT_BUTTON, self.archiveNow)
        self.checkArchiveStatus.Bind(wx.EVT_BUTTON, self.checkIfURLIsInArchive)
        self.viewArchive.Bind(wx.EVT_BUTTON, self.viewArchiveInBrowser)
        # hJob = HeritrixJob([self.uri.GetValue()])

    def testCallback(self):
        print "callback executed!"

    def archiveNow(self, button):
        self.archiveNowButton.SetLabel(buttonLabel_archiveNow_initializing)
        self.archiveNowButton.Disable()
        thread.start_new_thread(self.archiveNow2Async,())

    def archiveNow2Async(self):
        self.writeHeritrixLogWithURI()
        # First check to be sure Java SE is installed.
        if self.javaInstalled():
          if not Heritrix().accessible():
            self.launchHeritrix()
          mainAppWindow.advConfig.startTomcat(None)
          time.sleep(4)
          self.startHeritrixJob()
          mainAppWindow.advConfig.heritrixPanel.populateListboxWithJobs()

          #if sys.platform.startswith('darwin'): #show a notification of success in OS X
          #  Notifier.notify('Archival process successfully initiated.',title="WAIL")
        else:
          print "Java SE 6 needs to be installed. WAIL should invoke the installer here."

        wx.CallAfter(self.onLongRunDone)

    def onLongRunDone(self):
        print "DONE!"
        self.archiveNowButton.SetLabel(buttonLabel_archiveNow)
        self.archiveNowButton.Enable()

    def writeHeritrixLogWithURI(self):
        self.hJob = HeritrixJob([self.uri.GetValue()])
        self.hJob.write()

    def javaInstalled(self):
        # First check to be sure Java SE is installed. Move this logic elsewhere in production
        noJava = msg_noJavaRuntime
        p = Popen(["java","--version"], stdout=PIPE, stderr=PIPE)
        stdout, stderr = p.communicate()
        return (noJava not in stdout) and (noJava not in stderr)

    def launchHeritrix(self):
        cmd = heritrixBinPath+" -a "+heritrixCredentials_username+":"+heritrixCredentials_password
        #TODO: shell=True was added for OS X, verify that functionality persists on Win64
        ret = subprocess.Popen(cmd, shell=True)
        time.sleep(3)
        mainAppWindow.advConfig.generalPanel.updateServiceStatuses()

    def startHeritrixJob(self):
        self.buildHeritrixJob()
        self.launchHeritrixJob()

    def launchHeritrixJob(self):
        logging.basicConfig(level=logging.DEBUG)
        print "Launching heririx job"
        data = {"action":"launch"}
        headers = {"Accept":"application/xml","Content-type":"application/x-www-form-urlencoded"}
        r =requests.post('https://localhost:8443/engine/job/' + self.hJob.jobNumber,
            auth=HTTPDigestAuth(heritrixCredentials_username,heritrixCredentials_password),
            data=data,headers=headers,verify=False,stream=True)

        print r
        print r.headers
        print r.text

    def buildHeritrixJob(self):
        logging.basicConfig(level=logging.DEBUG)
        print "Building heririx job"
        data = {"action":"build"}
        headers = {"Accept":"application/xml","Content-type":"application/x-www-form-urlencoded"}
        r =requests.post('https://localhost:8443/engine/job/'+self.hJob.jobNumber,auth=HTTPDigestAuth(heritrixCredentials_username,heritrixCredentials_password),data=data,headers=headers,verify=False,stream=True)

        print r
        print r.headers
        print r.text

        #curl -v -d "action=launch" -k -u lorem:ipsum --anyauth --location -H "Accept: application/xml" https://127.0.0.1:8443/engine/job/1425431848
        return

    def checkIfURLIsInArchive(self, button):
        url = "http://localhost:8080/wayback/*/" + self.uri.GetValue()
        req = urllib2.Request(url)
        statusCode = None
        try:
            resp = urllib2.urlopen(req)
            statusCode = resp.getcode()
        except urllib2.HTTPError, e:
            statusCode = e.code
        except: # When the server is unavailable, keep the default. This is necessary, as unavailability will still cause an exception
            ''''''
        #print statusCode
        print statusCode
        if statusCode is None:
            launchWaybackDialog = wx.MessageDialog(None, msg_waybackNotStarted_body, msg_waybackNotStarted_title, wx.YES_NO|wx.YES_DEFAULT)
            launchWayback = launchWaybackDialog.ShowModal()
            if launchWayback == wx.ID_YES:
                Wayback().fix(None)
                self.checkIfURLIsInArchive(button)
        elif 200 != statusCode:
            wx.MessageBox(msg_uriNotInArchives,"Checking for " + self.uri.GetValue())
        else:
            wx.MessageBox(msg_uriInArchives_body,msg_uriInArchives_title)

    def viewArchiveInBrowser(self, button):
        if Wayback().accessible():
            webbrowser.open_new_tab(uri_wayback_allMementos + self.uri.GetValue())
        else:
            d = wx.MessageDialog(self, "Launch now?",
              "Wayback is not running", wx.YES_NO|wx.YES_DEFAULT|wx.ICON_QUESTION)
            result = d.ShowModal()
            d.Destroy()
            if result == wx.ID_YES: # Launch Wayback
                Wayback().fix(None)
                # TODO: artificial delay here while we wait for Wayback to launch
                # TODO: change button to fixing
                self.archiveNowButton.SetLabel("Initializing Wayback...")
                #self.viewArchiveInBrowser(None)


class WAILGUIFrame_Advanced(wx.Panel):
    class GeneralPanel(wx.Panel, threading.Thread):
        def __init__(self, parent):
            wx.Panel.__init__(self, parent)
            colWidth = 60
            rowHeight = 20#18
            cellSize = (150, rowHeight)

            col0 = colWidth*0+10
            wx.StaticText(self, 100, tabLabel_advanced_general_serviceStatus, (col0-10,    rowHeight*0),      cellSize)
            wx.StaticText(self, 100, tabLabel_advanced_wayback,       (col0, rowHeight*1),      cellSize)
            wx.StaticText(self, 100, tabLabel_advanced_heritrix,        (col0, rowHeight*2),      cellSize)

            col1 = 65+colWidth*1

            thread.start_new_thread(self.updateServiceStatuses,())

            col2 = col1+colWidth
            cellSize_versionFix = (50,rowHeight)
            wx.StaticText(self, 100, "VERSION",                 (col2,     rowHeight*0),     cellSize_versionFix)
            wx.StaticText(self, 100, self.getWaybackVersion(),                     (col2,     rowHeight*1),     cellSize_versionFix)
            wx.StaticText(self, 100, self.getHeritrixVersion(True), (col2,     rowHeight*2),     cellSize_versionFix)

            col3 = col2+colWidth
            buttonSize = (50, rowHeight-6)
            buttonSize = (50, rowHeight) #redefining for Windows, needs regression testing on OS X
            smallFont = wx.Font(10, wx.SWISS, wx.NORMAL, wx.NORMAL)
            self.fix_wayback = wx.Button(self, 1, buttonLabel_fix,                (col3,     rowHeight*1),     buttonSize,wx.BU_EXACTFIT)
            self.fix_wayback.SetFont(smallFont)
            self.fix_heritrix = wx.Button(self, 1, buttonLabel_fix,                (col3,     rowHeight*2),     buttonSize,wx.BU_EXACTFIT)
            self.fix_heritrix.SetFont(smallFont)

            #self.stopAllServices = wx.Button(self, 1, "Stop All Services",                (col2,     rowHeight*4+10),     (150,rowHeight))

            self.fix_wayback.Bind(wx.EVT_BUTTON, Wayback().fix)
            self.fix_heritrix.Bind(wx.EVT_BUTTON, Heritrix().fix)

            col4 = col3+colWidth

            self.kill_wayback = wx.Button(self, 1, buttonLabel_kill,                (col4,     rowHeight*1),     buttonSize, wx.BU_EXACTFIT)
            self.kill_wayback.SetFont(smallFont)
            self.kill_heritrix = wx.Button(self, 1, buttonLabel_kill,                (col4,     rowHeight*2),     buttonSize, wx.BU_EXACTFIT)
            self.kill_heritrix.SetFont(smallFont)

            self.kill_wayback.Bind(wx.EVT_BUTTON, Wayback().kill)
            self.kill_heritrix.Bind(wx.EVT_BUTTON, Heritrix().kill)


            #wx.CallLater(2000, self.updateServiceStatuses)
            #pool.apply_async(self.updateServiceStatuses)
            thread.start_new_thread(self.updateServiceStatuses,())

        def getHeritrixVersion(self, abbr=True):
            for file in os.listdir(heritrixPath + "lib/"):
              if file.startswith("heritrix-commons"):
                regex = re.compile("commons-(.*)\.")
                return regex.findall(file)[0]

        def getWaybackVersion(self):
            for file in os.listdir(tomcatPath + "/webapps/lib/"):
              if file.startswith("openwayback-core"):
                regex = re.compile("core-(.*)\.")
                return regex.findall(file)[0]

        def getTomcatVersion(self):
        #Apache Tomcat Version 7.0.30
            if not os.path.exists(tomcatPath+"/RELEASE-NOTES"): return "?"
            f = open(tomcatPath+"/RELEASE-NOTES",'r')
            version = ""
            for line in f.readlines():
                if "Apache Tomcat Version " in line:
                    version = re.sub("[^0-9^\.]", "", line)
                    break
            f.close()
            return version

        def updateServiceStatuses(self, serviceId=None, transitionalStatus=None):
            ##################################
            # Check if each service is enabled and set the GUI elements accordingly
            ##################################

            colWidth = 60
            rowHeight = 20
            col1 = 65+colWidth*1
            cellSize = (40, rowHeight)
            serviceEnabled = {True: serviceEnabledLabel_YES, False: serviceEnabledLabel_NO}

            heritrixAccessible = serviceEnabled[Heritrix().accessible()]
            waybackAccessible = serviceEnabled[Wayback().accessible()]

            if waybackAccessible is serviceEnabledLabel_YES:
                tomcatAccessible = waybackAccessible
            else:
                tomcatAccessible = serviceEnabled[Tomcat().accessible()]

            # Update a transitional status and short circuit
            if serviceId and transitionalStatus:
              if serviceId is "wayback":
                self.status_wayback.SetLabel(transitionalStatus)
                return
              elif serviceId is "heritrix":
                self.status_heritrix.SetLabel(transitionalStatus)
                return
              else:
                print "Invalid transitional service id specified. Updating status per usual."



            if hasattr(self,'status_heritrix'):
                #print "foooo"
                self.status_heritrix.SetLabel(heritrixAccessible)
                self.status_wayback.SetLabel(tomcatAccessible)
            else:
                wx.StaticText(self, 100, "STATE",          (col1,    rowHeight*0),      cellSize)
                self.status_wayback = wx.StaticText(self, 100, tomcatAccessible,       (col1,    rowHeight*1),      cellSize)
                self.status_heritrix = wx.StaticText(self, 100, heritrixAccessible,                   (col1,    rowHeight*2),      cellSize)


                #For eventual icons instead of text
                #bmp = wx.Bitmap("./build/icons/famYes.png", wx.BITMAP_TYPE_ANY)
                #bmapBtn = wx.BitmapButton(self, id=wx.ID_ANY, bitmap=bmp,pos=(col1,    rowHeight*3),size=(bmp.GetWidth()+14, bmp.GetHeight()+14),style=wx.BU_EXACTFIT)
                #bmapBtn.SetMargins(0,0)
                #bmapBtn.SetBackgroundColour('RED')

            if not hasattr(self,'fix_heritrix'):
                print "First call, UI has not been setup"
                return #initial setup call will return here, ui elements haven't been created

             #enable/disable FIX buttons based on service status
            if heritrixAccessible is serviceEnabledLabel_YES:
                self.fix_heritrix.Disable()
                self.kill_heritrix.Enable()
            else:
                self.fix_heritrix.Enable()
                self.kill_heritrix.Disable()

            if tomcatAccessible is serviceEnabledLabel_YES:
                self.fix_wayback.Disable()
                self.kill_wayback.Enable()
            else:
                self.fix_wayback.Enable()
                self.kill_wayback.Disable()


             ##################################
    class WaybackPanel(wx.Panel):
        def __init__(self, parent):
            wx.Panel.__init__(self, parent)
            bsize = self.width, self.height = (340, 25*.75)
            #wx.Button(self, 1, "Show All Archived URIs",   (0,0),bsize)
            #wx.Button(self, 1, "Setup Options (e.g. port), modify wayback.xml, reboot tomcat",   (0,25),bsize)
            #wx.Button(self, 1, "Control Tomcat",   (0,50),bsize)
            self.viewWaybackInBrowserButton = wx.Button(self, 1, buttonLabel_wayback,   (0, 0), bsize)
            self.editWaybackConfiguration = wx.Button(self, 1, buttonLabel_editWaybackConfig,   (0, 25), bsize)
            #self.resetWaybackConfiguration = wx.Button(self, 1, buttonLabel_resetWaybackConfig,   (0, 50), bsize)

            self.viewWaybackInBrowserButton.Bind(wx.EVT_BUTTON, self.openWaybackInBrowser)
            self.editWaybackConfiguration.Bind(wx.EVT_BUTTON, self.openWaybackConfiguration)
            #self.resetWaybackConfiguration.Bind(wx.EVT_BUTTON, waybackConfigWriter.writeConfig)

        def openWaybackInBrowser(self, button):
            if Wayback().accessible():
                webbrowser.open_new_tab(uri_wayback)
                self.viewWaybackInBrowserButton.SetLabel(buttonLabel_wayback)
                self.viewWaybackInBrowserButton.Enable()
            else:
                d = wx.MessageDialog(self, "Launch now?",
                                      "Wayback is not running", wx.YES_NO|wx.YES_DEFAULT|wx.ICON_QUESTION)
                result = d.ShowModal()
                d.Destroy()
                if result == wx.ID_YES: # Launch Wayback
                    Wayback().fix(None, lambda: self.openWaybackInBrowser(None))
                    self.viewWaybackInBrowserButton.SetLabel(buttonLabel_wayback_launching)
                    self.viewWaybackInBrowserButton.Disable()
                    #time.sleep(3)
                    #self.openWaybackInBrowser(None)
        def openWaybackConfiguration(self,button):
            filepath = tomcatPath+"/webapps/ROOT/WEB-INF/wayback.xml"
            if sys.platform.startswith('darwin'):
             subprocess.call(('open', filepath))
            elif os.name == 'nt':
             os.startfile(filepath)
            elif os.name == 'posix':
             subprocess.call(('xdg-open', filepath))
    class HeritrixPanel(wx.Panel):
        def __init__(self, parent):
            wx.Panel.__init__(self, parent)

            self.listbox = wx.ListBox(self, 100)
            self.populateListboxWithJobs()

            self.statusMsg = wx.StaticText(self, -1, "", pos=(150, 0))

            self.listbox.Bind(wx.EVT_LISTBOX, self.clickedListboxItem)
            self.listbox.Bind(wx.EVT_RIGHT_UP, self.manageJobs)

            #Button layout
            bsize = self.width, self.height = (125, 25*.75)
            self.setupNewCrawlButton = wx.Button(self, 1, buttonLabel_heritrix_newCrawl,   (0, 70), bsize)
            self.launchWebUIButton = wx.Button(self, 1, buttonLabel_heritrix_launchWebUI,   (0, 92), bsize)

            #Button functionality
            self.setupNewCrawlButton.Bind(wx.EVT_BUTTON, self.setupNewCrawl)
            self.launchWebUIButton.Bind(wx.EVT_BUTTON, self.launchWebUI)

        def populateListboxWithJobs(self):
            list = Heritrix().getListOfJobs()
            list.reverse() # set to reverse chronological so newest jobs are at the top
            self.listbox.Set(list)

        def clickedListboxItem(self, event):
            self.hideNewCrawlUIElements()
            self.statusMsg.Show()

            active = self.listbox.GetString(self.listbox.GetSelection())
            print tail(heritrixJobPath + active + "/job.log")
            jobLaunches = Heritrix().getJobLaunches(active)
            self.statusMsg.SetLabel(
                str(tail(heritrixJobPath+active+"/job.log"))
                 + "\n" + str(len(jobLaunches)) + " job launches\n"
                 +  Heritrix().getCurrentStats(active)
                 )

        def launchWebUI(self, button):
            self.launchWebUIButton.SetLabel(buttonLabel_heritrix_launchWebUI_launching)
            self.launchWebUIButton.Disable()
            thread.start_new_thread(self.launchWebUIAsync,())

        def launchWebUIAsync(self):
            if not Heritrix().accessible():
                mainAppWindow.basicConfig.launchHeritrix()
            webbrowser.open_new_tab(uri_heritrix)
            self.launchWebUIButton.SetLabel(buttonLabel_heritrix_launchWebUI)
            self.launchWebUIButton.Enable()

        def launchHeritrixProcess(self, button):
            Heritrix().kill(None)
            time.sleep(3)
            mainAppWindow.basicConfig.launchHeritrix()

        def manageJobs(self, evt):
            if self.listbox.GetCount() == 0: # Do not show context menu without context
                return

            menu = wx.Menu()
            #menu.Append( 1, "Restart Job" ) #TODO
            #menu.Bind(wx.EVT_MENU, self.restartJob, id=1)
            menu.Append( 1, menu_forceCrawlFinish )
            menu.Bind(wx.EVT_MENU, self.forceCrawlFinish, id=1)
            menu.Append( 2, menu_destroyJob )
            menu.Bind(wx.EVT_MENU, self.deleteHeritrixJob, id=2)
            #menu.Append( 3, "Open crawl configuration" )
            #menu.Bind(wx.EVT_MENU, self.openConfigInTextEditor, id=3)
            mainAppWindow.PopupMenu( menu, mainAppWindow.ScreenToClient(wx.GetMousePosition()) )
            menu.Destroy()

        def forceCrawlFinish(self, evt):
            jobId = str(self.listbox.GetString(self.listbox.GetSelection()))
            self.sendActionToHeritrix("terminate", jobId)
            self.sendActionToHeritrix("teardown", jobId)

        def sendActionToHeritrix(self, action, jobId):
            data = {"action": action}
            headers = {"Accept":"application/xml","Content-type":"application/x-www-form-urlencoded"}
            r =requests.post('https://localhost:8443/engine/job/' + jobId, auth = HTTPDigestAuth(heritrixCredentials_username, heritrixCredentials_password), data=data, headers=headers, verify=False, stream=True)

        def deleteHeritrixJob(self, evt):
            jobPath = heritrixJobPath + str(self.listbox.GetString(self.listbox.GetSelection()))
            print "Deleting Job at "+jobPath
            shutil.rmtree(jobPath)
            self.populateListboxWithJobs()

        def openConfigInTextEditor(self, evt):
            #TODO, most systems don't know how to open a cxml file. Is there a way to create a system mapping from python?
            # Issue #22 prevents the context of the right-click item from being obtained and used here.
            file = heritrixJobPath + str(self.listbox.GetString(self.listbox.GetSelection())) + "/crawler-beans.cxml"
            if sys.platform.startswith('darwin'):
                subprocess.call(('open', file))
            elif os.name == 'nt':
                os.startfile(file)
            elif os.name == 'posix':
                subprocess.call(('xdg-open', file))

        def restartJob(self, evt):
            print "Restarting job"

        def setupNewCrawl(self, evt):
            # TODO: check if the UI elements already exist before adding them
            if hasattr(self, 'newCrawlTextCtrlLabel'):
                print "The UI has already been setup."
                return

            self.statusMsg.Hide()

            self.newCrawlTextCtrlLabel = wx.StaticText(self, -1, "Enter one URI per line to crawl", pos=(135, 0))
            multiLineAndNoWrapStyle = wx.TE_MULTILINE + wx.TE_DONTWRAP
            self.newCrawlTextCtrl = wx.TextCtrl(self, -1, pos=(135, 20), size=(225, 90), style=multiLineAndNoWrapStyle)
            #self.crawlOptionsButton = wx.Button(self, -1, "More options",  pos=(150,125))
            self.startCrawlButton = wx.Button(self, -1, "Start Crawl",  pos=(265, 110))
            self.startCrawlButton.SetDefault()
            self.startCrawlButton.Bind(wx.EVT_BUTTON, self.crawlURIsListed)

            self.showNewCrawlUIElements()

        def hideNewCrawlUIElements(self):
            if not hasattr(self,'newCrawlTextCtrlLabel'): return
            self.newCrawlTextCtrlLabel.Hide()
            self.newCrawlTextCtrl.Hide()
            #self.crawlOptionsButton.Hide()
            self.startCrawlButton.Hide()

        def showNewCrawlUIElements(self):
            self.newCrawlTextCtrlLabel.Show()
            self.newCrawlTextCtrl.Show()
            #self.crawlOptionsButton.Show()
            self.startCrawlButton.Show()

        def crawlURIsListed(self, evt):
            uris = self.newCrawlTextCtrl.GetValue().split("\n")
            self.hJob = HeritrixJob(uris)
            self.hJob.write()
            self.populateListboxWithJobs()

            if not Heritrix().accessible():
                mainAppWindow.basicConfig.launchHeritrix()

            self.hJob.buildHeritrixJob()
            self.hJob.launchHeritrixJob()


    class MiscellaneousPanel(wx.Panel):
        def __init__(self, parent):
            wx.Panel.__init__(self, parent)
            bsize = self.width, self.height = (340, 25*.75)
            viewArchivesFolderButtonButton = wx.Button(self, 1, buttonLabel_viewArchiveFiles,   (0, 0), bsize)
            #wx.Button(self, 1, "Control Other Tools",   (0,50), bsize)

            viewArchivesFolderButtonButton.Bind(wx.EVT_BUTTON, self.openArchivesFolder)
            self.testUpdate = wx.Button(self, 1, "Check for Updates",   (0, 25), bsize)
            self.testUpdate.Bind(wx.EVT_BUTTON, self.checkForUpdates)
            self.testUpdate.Disable()

        def openArchivesFolder(self, button):
            if not os.path.exists(warcsFolder): os.makedirs(warcsFolder)

            if sys.platform.startswith('win32'):
                 os.startfile(warcsFolder)
            else:
              subprocess.call(["open", warcsFolder])
              #subprocess.check_call(['open', '--', tomcatPath+"/webapps/root/"])
              #subprocess.Popen(["open", tomcatPath+"/webapps/root/"])

        def checkForUpdates(self, button):
            # check if an updates version is available

            # if an updated version is available and the user wants it, copy the /Application/WAIL.app/Contents folder

            d = wx.MessageDialog(self, "Do you want to update WAIL? All of your WARCs will remain in-place.",
                                      "There is an update available for the main WAIL application", wx.YES_NO|wx.YES_DEFAULT|wx.ICON_QUESTION)
            result = d.ShowModal()
            d.Destroy()
            if result == wx.ID_YES: # Launch Wayback
                print "The user wants to update!"

                #TODO: show progress bar or separate window for updater
                wailcorefile = urllib2.urlopen("http://matkelly.com/wail/release/WAILCore1_1.tar.gz")
                output = open('/Applications/WAIL.app/support/WAILCore1_1.tar.gz','wb')
                output.write(wailcorefile.read())
                output.close()

                print "Done fetching WAIL core"

                #TODO untar to temp dir

                #TODO move new temp directory to Contents/

                # TODO: check if this directory already exists
                copyanything("/Applications/WAIL.app/Contents/","/Applications/WAIL.app/Contents_bkp/")
                shutil.rmtree("/Applications/WAIL.app/Contents/")

                tar = tarfile.open("/Applications/WAIL.app/support/WAILCore1_1.tar.gz")
                tar.extractall('/Applications/WAIL.app/')
                tar.close()

                print "done extracting the tar file of wailcore"

    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        self.Notebook = wx.Notebook(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(self.Notebook, 10, flag=wx.EXPAND)

        self.SetSizer(vbox)

        self.generalPanel = WAILGUIFrame_Advanced.GeneralPanel(self.Notebook)
        self.waybackPanel = WAILGUIFrame_Advanced.WaybackPanel(self.Notebook)
        self.heritrixPanel = WAILGUIFrame_Advanced.HeritrixPanel(self.Notebook)
        self.miscellaneousPanel = WAILGUIFrame_Advanced.MiscellaneousPanel(self.Notebook)
        # Add advanced config page/tab
    	#self.advConfig = WAILGUIFrame_Advanced(self.Notebook) #PDA2013 advanced tab

        self.Notebook.AddPage(self.generalPanel, tabLabel_advanced_general)
        self.Notebook.AddPage(self.waybackPanel, tabLabel_advanced_wayback)
        self.Notebook.AddPage(self.heritrixPanel, tabLabel_advanced_heritrix)
        self.Notebook.AddPage(self.miscellaneousPanel, tabLabel_advanced_miscellaneous)

        self.x, self.y = (15, 5)
        bsize = self.width, self.height = (150, 25*.80)

        smallFont = wx.Font(fontSize, wx.SWISS, wx.NORMAL, wx.NORMAL)

##################################
# "View Archive" Group
##################################
    def tomcatMessageOff(self):
        #self.tomcatStatus.SetLabel(msg_waybackDisabled)
        self.tomcatStatus.SetForegroundColour((255, 0, 0))
        self.startTomcatButton.SetLabel(self.startTomcatLabel)

    def tomcatMessageOn(self):
        #self.tomcatStatus.SetLabel(msg_waybackEnabled)
        self.tomcatStatus.SetForegroundColour((0, 200, 0))
        self.startTomcatButton.SetLabel(self.stopTomcatLabel)

    def startTomcat(self, button):
        #self.tomcatStatus.SetLabel(msg_startingTomcat)
        cmd = tomcatPathStart
        ret = subprocess.Popen(cmd)
        waitingForTomcat = True
        while waitingForTomcat:
            if Wayback().accessible(): waitingForTomcat = False
            time.sleep(2)

        self.waybackPanel.viewWaybackInBrowserButton.Enable() #TODO: error here
        #self.tomcatMessageOn()
    # toggleTomcat needs to be broken up into start and stop Tomcat function, already done above

    def toggleTomcat(self, button, suppressAlert=False): #Optimize me, Seymour
        cmd = ""

        if self.startTomcatButton.GetLabel() == self.startTomcatLabel :
            self.tomcatStatus.SetLabel(msg_startingTomcat)
            cmd = tomcatPathStart
            ret = subprocess.Popen(cmd)
            waitingForTomcat = True
            while waitingForTomcat:
                if Wayback.accessible(): waitingForTomcat = False
                time.sleep(2)
            self.viewWaybackInBrowserButton.Enable()
            #self.tomcatMessageOn()
        else:
            self.tomcatStatus.SetLabel(msg_stoppingTomcat)
            cmd = tomcatPathStop
            ret = subprocess.Popen(cmd)
            waitingForTomcat = True

            tomcatChecks = 0
            tomcatStopped = False
            while waitingForTomcat and tomcatChecks < 6:
                if Wayback.accessible():
                    tomcatChecks += 1
                else:
                    waitingForTomcat = False
                    tomcatStopped = True
                time.sleep(2)
            if tomcatStopped:
                self.viewWaybackInBrowserButton.Disable()
                self.tomcatMessageOff()
            else:
                if not suppressAlert: message = wx.MessageBox("Tomcat could not be stopped", "Command Failed")
                #self.tomcatMessageOn()

    def launchHeritrix(self, button):
        #self.heritrixStatus.SetLabel("Launching Heritrix")
        cmd = heritrixBinPath+" -a "+heritrixCredentials_username+":"+heritrixCredentials_password
        #TODO: shell=True was added for OS X, verify that functionality persists on Win64
        ret = subprocess.Popen(cmd, shell=True)
        time.sleep(6)             #urlib won't respond to https, hard-coded sleep until I can ping like Tomcat
        self.viewHeritrixButton.Enable()

    def viewWayback(self, button):
        webbrowser.open_new_tab(uri_wayback)

    def viewHeritrix(self, button):
        webbrowser.open_new_tab(uri_heritrix)

    def createListBox(self):

        self.uriListBoxTitle = wx.StaticText(self, 7, 'URIs to Crawl:',  (self.x, 5+self.height*7+30))
        self.uriListBox = wx.ListBox(self, 99, (self.x, 5+self.height*8+25), (400-50, 100), [""])
        #self.uriListBox.Bind(wx.EVT_LISTBOX_DCLICK,self.addURI)
        self.uriListBox.Bind(wx.EVT_LISTBOX, self.addURI)
        self.SetSize((self.GetSize().x, self.GetSize().y+300))
        #self.archiveViewGroup.SetSize((self.archiveViewGroup.GetSize().x,100))
        self.archiveViewGroup.SetSize((self.archiveViewGroup.GetSize().x, 235))
        mainAppWindow.SetSize((mainAppWindow.GetSize().x, 400))

    def setupOneOffCrawl(self, button):
        if(self.uriListBox <> None): return #this function has already been done
        self.createListBox()

        #This should say, "Commence Crawl" but it currently only writes the config file
        self.writeConfig = wx.Button(self, 33, "Write Heritrix Config",   (self.GetSize().x-175, 280), (self.width, self.height))
        self.writeConfig.SetFont(wx.Font(fontSize, wx.SWISS, wx.NORMAL, wx.NORMAL))
        self.writeConfig.Bind(wx.EVT_BUTTON, self.crawlURIs)
        self.writeConfig.Disable()
        self.launchCrawlButton = wx.Button(self, 33, "Launch Crawl",   (self.GetSize().x-175, 305), (self.width, self.height))
        self.launchCrawlButton.SetFont(wx.Font(fontSize, wx.SWISS, wx.NORMAL, wx.NORMAL))
        self.launchCrawlButton.Bind(wx.EVT_BUTTON, self.launchCrawl)
        self.launchCrawlButton.Disable()

    def crawlURIs(self, button):
        uris = self.uriListBox.GetStrings()
        self.hJob = HeritrixJob(uris)
        self.hJob.write()
        self.writeConfig.Disable()
        self.uriListBox.Set([""])
        self.launchCrawlButton.Enable()

    def launchCrawl(self, button):
        mainAppWindow.basicConfig.hJob = self.hJob
        mainAppWindow.basicConfig.launchHeritrix()
        mainAppWindow.basicConfig.startHeritrixJob()

    def addURI(self, listbox):
        defaultMessage = ""
        try:
            defaultMessage = self.uriListBox.GetString(self.uriListBox.GetSelection())
        except:
            defaultMessage = ""
        message = wx.GetTextFromUser("Enter a URI to be crawled", default_value=defaultMessage)
        if message == "" and message == defaultMessage: return
        url = urlparse(message)
        self.uriListBox.InsertItems([url.geturl()], 0)
        self.writeConfig.Enable()


class Service():
    def accessible(self):
        try:
            print "Trying to access " + self.__class__.__name__ + " service at " + self.uri
            handle = urllib2.urlopen(self.uri, None, 3)
            print self.__class__.__name__ + " is a go! "
            return True
        except IOError, e:
            if hasattr(e, 'code'): # HTTPError
                print "Pseudo-Success in accessing " + self.uri
                return True
           # if hasattr(e,

            print "Failed to access " + self.__class__.__name__+" service at " + self.uri
            return False


class Wayback(Service):
    uri = uri_wayback

    def fix(self, button, *cb):
        thread.start_new_thread(self.fixAsync, cb)

    def fixAsync(self, cb=None):
        mainAppWindow.advConfig.generalPanel.updateServiceStatuses("wayback","FIXING")
        cmd = tomcatPathStart;
        ret = subprocess.Popen(cmd)
        time.sleep(3)
        wx.CallAfter(mainAppWindow.advConfig.generalPanel.updateServiceStatuses)
        if cb:
          wx.CallAfter(cb)
# mainAppWindow.advConfig.generalPanel.updateServiceStatuses()

    def kill(self,button):
        thread.start_new_thread(self.killAsync,())

    def killAsync(self):
        mainAppWindow.advConfig.generalPanel.updateServiceStatuses("wayback","KILLING")
        cmd = tomcatPathStop
        ret = subprocess.Popen(cmd)
        time.sleep(3)
        wx.CallAfter(mainAppWindow.advConfig.generalPanel.updateServiceStatuses)
        #mainAppWindow.advConfig.generalPanel.updateServiceStatuses()

    def index(self):
        paths = [fn+"\t"+os.path.join(warcsFolder,fn) for fn in next(os.walk(warcsFolder))[2]] #could probably put some .warc restrcitions here

        f = open(warcsFolder+"/../path-index.txt", 'w+')
        f.write("\n".join(paths))

        #TODO: check if the file was updated. If so, invoke cdx-indexer
        threading.Timer(5.0, Wayback().index).start()


class Tomcat(Service):
    uri = uri_wayback


class Heritrix(Service):
    #uri = uri_heritrix_accessiblityURI
    uri = "https://127.0.0.1:8443" #TODO: remove magic hard-coded Heritrix address/port

    def getListOfJobs(self):
        def justFile(fullPath):
            return os.path.basename(fullPath)
        #str = '\n'.join(map(justFile,glob.glob(os.path.join(heritrixJobPath, '*'))))
        return map(justFile, glob.glob(os.path.join(heritrixJobPath, '*')))
    ''' # getListOfJobs - rewrite to use the Heritrix API, will need to parse XML
        -H "Accept: application/xml"
        # replicate curl -v -d "action=rescan" -k -u lorem:ipsum --anyauth --location -H "Accept: application/xml" https://localhost:8443/engine
    '''

    def getJobLaunches(self, jobId):
        jobPath = heritrixJobPath+jobId
        return [f for f in os.listdir(heritrixJobPath+jobId) if re.search(r'^[0-9]+$', f)]

    def getCurrentStats(self, jobId):
        launches = self.getJobLaunches(jobId)
        ret = ""
        for launch in launches:
            #print heritrixJobPath+jobId+"/"+launch+"/logs/progress-statistics.log"
            print heritrixJobPath+jobId+"/"+launch+"/logs/progress-statistics.log"
            lastLine = tail(heritrixJobPath+jobId+"/"+launch+"/logs/progress-statistics.log")

            ll = lastLine[0].replace(" ","|")
            logData = re.sub(r'[|]+', '|', ll).split("|")
            timeStamp, discovered, queued, downloaded = logData[0:4]
            ret = ret + "JobID: "+jobId+"\n   Discovered: "+discovered+"\n   Queued: "+queued+"\n   Downloaded: "+downloaded+"\n"

        return ret

    def fix(self, button, *cb):
        thread.start_new_thread(self.fixAsync, cb)

    def fixAsync(self, cb):
        mainAppWindow.advConfig.generalPanel.updateServiceStatuses("heritrix","FIXING")
        mainAppWindow.basicConfig.launchHeritrix()
        time.sleep(3)
        wx.CallAfter(mainAppWindow.advConfig.generalPanel.updateServiceStatuses)
        if cb:
          wx.CallAfter(cb)

    def kill(self,button):
        thread.start_new_thread(self.killAsync,())

    def killAsync(self):
        mainAppWindow.advConfig.generalPanel.updateServiceStatuses("heritrix", "KILLING")
        #Ideally, the Heritrix API would have support for this. This will have to do. Won't work in Wintel
        cmd = """ps ax | grep 'heritrix' | grep -v grep | awk '{print "kill -9 " $1}' | sh"""
        print "Trying to kill Heritrix..."
        ret = subprocess.Popen(cmd,stderr=subprocess.STDOUT,shell=True)
        time.sleep(3)
        wx.CallAfter(mainAppWindow.advConfig.generalPanel.updateServiceStatuses)


class HeritrixJob:
    def write(self):
        self.jobNumber = str(int(time.time()))
        path = heritrixJobPath+self.jobNumber
        if not os.path.exists(path): os.makedirs(path)
        beansFilePath = path
        if sys.platform.startswith('win32'):
            beansFilePath += "\\"
        else:
            beansFilePath += "/"
        with open(beansFilePath+"crawler-beans.cxml","w") as f:
            f.write(self.sampleXML)
            #print beansFilePath+"crawler-beans.cxml"

    def launchHeritrixJob(self):
        logging.basicConfig(level=logging.DEBUG)
        print "Launching heririx job"
        data = {"action":"launch"}
        headers = {"Accept":"application/xml","Content-type":"application/x-www-form-urlencoded"}
        r =requests.post('https://localhost:8443/engine/job/'+self.jobNumber,auth=HTTPDigestAuth(heritrixCredentials_username, heritrixCredentials_password),data=data,headers=headers,verify=False,stream=True)

    def buildHeritrixJob(self):
        logging.basicConfig(level=logging.DEBUG)
        print "Building heririx job"
        data = {"action":"build"}
        headers = {"Accept":"application/xml","Content-type":"application/x-www-form-urlencoded"}
        r =requests.post('https://localhost:8443/engine/job/'+self.jobNumber,auth=HTTPDigestAuth(heritrixCredentials_username, heritrixCredentials_password),data=data,headers=headers,verify=False,stream=True)


#from http://stackoverflow.com/questions/136168/get-last-n-lines-of-a-file-with-python-similar-to-tail
def tail(filename, lines=1, _buffer=4098):
    try:
        f = open(filename,"r")
    except:
        return "No job info yet\nYou must run a job before stats can be shown here"
    lines_found = []
    block_counter = -1
    while len(lines_found) < lines:
        try:
            f.seek(block_counter * _buffer, os.SEEK_END)
        except IOError:  # either file is too small, or too many lines requested
            f.seek(0)
            lines_found = f.readlines()
            break

        lines_found = f.readlines()
        if len(lines_found) > lines:
            break
        block_counter -= 1
    return lines_found[-lines:]

def copyanything(src, dst):
    try:
        shutil.copytree(src, dst)
    except OSError as exc: # python >2.5
        if exc.errno == errno.ENOTDIR:
            shutil.copy(src, dst)
        else: raise

mainAppWindow = None

if __name__ == "__main__":
    app = wx.App(redirect=False)
    mainAppWindow = TabController()
    mainAppWindow.ensureCorrectInstallation()
    mainAppWindow.Show()

    # Start indexer
    #Wayback().index()

    app.MainLoop()
