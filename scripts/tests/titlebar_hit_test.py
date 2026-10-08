#!/usr/bin/env python3
"""Click across a window's title bar under Marco and report which pixels close, maximize or minimize it."""
import os
import subprocess
import sys
import time

WINDOW = """
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
w = Gtk.Window(title="hit-test"); w.set_default_size(600, 300); w.move(200, 150)
w.connect("destroy", Gtk.main_quit); w.show_all(); Gtk.main()
"""


def sh(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()


def open_window():
    proc = subprocess.Popen([sys.executable, "-c", WINDOW], stderr=subprocess.DEVNULL)
    for _ in range(50):
        wid = sh("xdotool", "search", "--name", "^hit-test$").splitlines()
        if wid:
            time.sleep(0.25)
            return proc, wid[-1]
        time.sleep(0.1)
    raise SystemExit("the test window did not appear")


def frame(wid):
    info = sh("xwininfo", "-frame", "-id", wid)
    get = lambda key: int(info.split(key)[1].split()[0])  # noqa: E731
    return get("Absolute upper-left X:"), get("Absolute upper-left Y:"), get("Width:"), get("Height:")


def state(wid):
    if not sh("xdotool", "search", "--name", "^hit-test$"):
        return "close"
    props = sh("xprop", "-id", wid, "_NET_WM_STATE")
    if "HIDDEN" in props:
        return "minimize"
    if "MAXIMIZED" in props:
        return "maximize"
    return ""


def main():
    marco = subprocess.Popen(["marco", "--sm-disable"], stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    proc, wid = open_window()
    fx, fy, fw, _fh = frame(wid)
    client_y = int(sh("xwininfo", "-id", wid).split("Absolute upper-left Y:")[1].split()[0])
    title_h = client_y - fy
    hits = {}

    def click(x, y):
        nonlocal proc, wid
        sh("xdotool", "mousemove", str(x), str(y), "click", "1")
        time.sleep(0.12)
        what = state(wid)
        if what == "close":
            proc.wait(timeout=5)
            proc, wid = open_window()
        elif what == "minimize":
            sh("xdotool", "windowmap", wid)
            sh("wmctrl", "-i", "-a", wid)
            time.sleep(0.15)
        elif what == "maximize":
            sh("wmctrl", "-i", "-r", wid, "-b", "remove,maximized_vert,maximized_horz")
            time.sleep(0.15)
        if what:
            hits.setdefault(what, []).append((x - fx, y - fy))
        return what

    mid = fy + title_h // 2
    for x in range(fx + fw - 130, fx + fw + 1):  # one row through the middle of the title bar
        click(x, mid)
    for what in list(hits):  # one column through the middle of each button
        xs = [x for x, _ in hits[what]]
        cx = fx + (min(xs) + max(xs)) // 2
        for y in range(fy, fy + title_h + 3):
            click(cx, y)
    print(f"{os.environ.get('THEME', '?')}: frame {fw} px wide, title bar {title_h} px high")
    last_x = None
    for what in ("minimize", "maximize", "close"):
        if what not in hits:
            print(f"  {what:9s} not found")
            continue
        xs = [x for x, _ in hits[what]]
        ys = [y for _, y in hits[what]]
        gap = "" if last_x is None else f", gap to previous button {min(xs) - last_x - 1} px"
        print(f"  {what:9s} x {min(xs)}-{max(xs)} ({max(xs) - min(xs) + 1} px wide), y {min(ys)}-{max(ys)} "
              f"({max(ys) - min(ys) + 1} px high){gap}")
        last_x = max(xs)
    if "close" in hits:
        print(f"  right of close to the frame edge: {fw - 1 - max(x for x, _ in hits['close'])} px")
    proc.terminate()
    marco.terminate()


if __name__ == "__main__":
    main()
