#!/usr/bin/python3
import subprocess, threading, gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk, GLib
class App(Gtk.Window):
  def __init__(self):
    super().__init__(title='Spaced NVIDIA Driver Installer'); self.set_default_size(720,480); self.set_border_width(18)
    b=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10); self.add(b)
    h=Gtk.Label(); h.set_markup('<span size="x-large" weight="bold">Spaced NVIDIA Driver Installer</span>'); h.set_xalign(0); b.pack_start(h,False,False,0)
    d=Gtk.Label(label='Detects your NVIDIA GPU and installs the appropriate Debian/Devuan packaged driver. Nouveau remains the safe live-ISO default.'); d.set_line_wrap(True); d.set_xalign(0); b.pack_start(d,False,False,0)
    self.p=Gtk.ProgressBar(); self.p.set_show_text(True); b.pack_start(self.p,False,False,0)
    s=Gtk.ScrolledWindow(); s.set_vexpand(True); b.pack_start(s,True,True,0); self.t=Gtk.TextView(); self.t.set_editable(False); self.t.set_monospace(True); self.buf=self.t.get_buffer(); s.add(self.t)
    self.btn=Gtk.Button(label='Detect and Install NVIDIA Driver'); self.btn.connect('clicked',self.go); b.pack_start(self.btn,False,False,0)
    self.connect('destroy',Gtk.main_quit)
  def add(self,x): self.buf.insert(self.buf.get_end_iter(),x+'\n')
  def go(self,*_): self.btn.set_sensitive(False); threading.Thread(target=self.work,daemon=True).start()
  def work(self):
    cmd=['pkexec','/usr/lib/spaced-linux/spaced-nvidia-helper']
    p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    for line in p.stdout: GLib.idle_add(self.add,line.rstrip())
    rc=p.wait(); GLib.idle_add(self.p.set_fraction,1.0); GLib.idle_add(self.p.set_text,'Complete — reboot required' if rc==0 else 'Installation failed'); GLib.idle_add(self.btn.set_sensitive,True)
App().show_all(); Gtk.main()
