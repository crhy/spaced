#!/usr/bin/python3
import os, re, subprocess, threading
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk, GLib

class App(Gtk.Window):
    def __init__(self):
        super().__init__(title='Spaced Update')
        self.set_default_size(760, 520)
        self.set_border_width(18)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12); self.add(box)
        title=Gtk.Label(); title.set_markup('<span size="x-large" weight="bold">Spaced Update</span>'); title.set_xalign(0); box.pack_start(title,False,False,0)
        subtitle=Gtk.Label(label='Updates Spaced Linux through APT and Flathub in one place.'); subtitle.set_xalign(0); box.pack_start(subtitle,False,False,0)
        self.status=Gtk.Label(label='Ready to check for updates.'); self.status.set_xalign(0); box.pack_start(self.status,False,False,0)
        self.progress=Gtk.ProgressBar(); self.progress.set_show_text(True); box.pack_start(self.progress,False,False,0)
        scroll=Gtk.ScrolledWindow(); scroll.set_hexpand(True); scroll.set_vexpand(True); box.pack_start(scroll,True,True,0)
        self.log=Gtk.TextView(); self.log.set_editable(False); self.log.set_monospace(True); self.buf=self.log.get_buffer(); scroll.add(self.log)
        row=Gtk.Box(spacing=8); box.pack_start(row,False,False,0)
        self.runbtn=Gtk.Button(label='Install All Updates'); self.runbtn.connect('clicked',self.start); row.pack_end(self.runbtn,False,False,0)
        close=Gtk.Button(label='Close'); close.connect('clicked',lambda *_: Gtk.main_quit()); row.pack_end(close,False,False,0)
        self.connect('destroy',Gtk.main_quit)
    def append(self,text):
        end=self.buf.get_end_iter(); self.buf.insert(end,text+'\n'); self.log.scroll_to_iter(self.buf.get_end_iter(),0,False,0,0)
    def setstep(self,pct,msg):
        self.progress.set_fraction(max(0,min(100,pct))/100); self.progress.set_text(f'{pct}% — {msg}'); self.status.set_text(msg)
    def start(self,*_):
        self.runbtn.set_sensitive(False); self.buf.set_text(''); threading.Thread(target=self.worker,daemon=True).start()
    def run_cmd(self,cmd,label,base,span):
        GLib.idle_add(self.status.set_text,label)
        p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
        for line in p.stdout:
            line=line.rstrip(); m=re.match(r'SPACED_STEP:(\d+):(.*)',line)
            if m: GLib.idle_add(self.setstep,int(m.group(1)),m.group(2))
            else: GLib.idle_add(self.append,line)
        return p.wait()
    def worker(self):
        try:
            rc=self.run_cmd(['pkexec','/usr/lib/spaced-linux/spaced-update-helper'],'Updating system packages',0,90)
            if rc: raise RuntimeError(f'System update helper exited with status {rc}')
            GLib.idle_add(self.setstep,92,'Updating your Flatpak applications')
            if shutil_which('flatpak'):
                p=subprocess.Popen(['flatpak','update','-y','--user'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
                for line in p.stdout: GLib.idle_add(self.append,line.rstrip())
                p.wait()
            GLib.idle_add(self.setstep,100,'Everything is up to date')
            GLib.idle_add(self.append,'Finished successfully.')
        except Exception as e:
            GLib.idle_add(self.status.set_text,'Update failed')
            GLib.idle_add(self.append,f'ERROR: {e}')
        finally: GLib.idle_add(self.runbtn.set_sensitive,True)
def shutil_which(name):
    from shutil import which
    return which(name)
App().show_all(); Gtk.main()
