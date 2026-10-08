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


def geometry(wid):
    """Client area (x, y, width) and the frame extents (left, right, top) the window manager publishes."""
    info = sh("xwininfo", "-id", wid)
    get = lambda key: int(info.split(key)[1].split()[0])  # noqa: E731
    extents = sh("xprop", "-id", wid, "_NET_FRAME_EXTENTS").split("=")[-1].split(",")
    left, right, top, _bottom = (int(v) for v in extents)
    return get("Absolute upper-left X:"), get("Absolute upper-left Y:"), get("Width:"), left, right, top


def state(wid):
    if not sh("xdotool", "search", "--name", "^hit-test$"):
        return "close"
    props = sh("xprop", "-id", wid, "_NET_WM_STATE")
    if "HIDDEN" in props:
        return "minimize"
    if "MAXIMIZED" in props:
        return "maximize"
    return ""


def start_window_manager():
    """Marco, or Compiz with its GTK decorator (what Spaced runs) when WM=compiz."""
    if os.environ.get("WM", "compiz") == "marco":
        procs = [subprocess.Popen(["marco", "--sm-disable"], stderr=subprocess.DEVNULL)]
        time.sleep(1.5)
        return procs
    procs = [subprocess.Popen(["compiz", "--replace", "--sm-disable", "decoration", "move", "resize", "place"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)]
    time.sleep(4)
    procs.append(subprocess.Popen(["gtk-window-decorator", "--replace"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    time.sleep(3)
    return procs


def main():
    managers = start_window_manager()
    proc, wid = open_window()
    cx, cy, cw, _left, right, top = geometry(wid)
    edge = cx + cw  # the client area's right edge; x is reported as pixels left of it
    hits = {}

    def click(x, y):
        nonlocal proc, wid
        sh("xdotool", "mousemove", str(x), str(y), "click", "1")
        time.sleep(0.15)
        what = state(wid)
        if what == "close":
            proc.wait(timeout=5)
            proc, wid = open_window()
        elif what == "minimize":
            sh("xdotool", "windowmap", wid)
            sh("wmctrl", "-i", "-a", wid)
            time.sleep(0.2)
        elif what == "maximize":
            sh("wmctrl", "-i", "-r", wid, "-b", "remove,maximized_vert,maximized_horz")
            time.sleep(0.2)
        if what:
            hits.setdefault(what, []).append((x - edge, y - cy))
        time.sleep(0.45)  # two quick clicks on the title would count as a double-click and maximize
        return what

    quick = os.environ.get("QUICK_COLUMN")  # e.g. -32: only sweep one column, that many pixels from the right edge
    if quick:
        for y in range(cy - top, cy + 3):
            click(edge + int(quick), y)
    for x in ([] if quick else range(edge - 125, edge + right + 1)):  # one row through the middle of the title bar
        click(x, cy - 14)
    for what in ([] if quick else list(hits)):  # one column through the middle of each button
        xs = [x for x, _ in hits[what]]
        centre = edge + (min(xs) + max(xs)) // 2
        for y in range(cy - top, cy + 3):
            click(centre, y)
    print(f"{os.environ.get('THEME', '?')} under {os.environ.get('WM', 'compiz')}: frame extents top {top} px, right {right} px")
    print("  (x = pixels from the window's right edge, negative is inside; y = pixels above the window's contents)")
    last = None
    for what in ("minimize", "maximize", "close"):
        if what not in hits:
            print(f"  {what:9s} not found")
            continue
        xs = [x for x, _ in hits[what]]
        ys = [-y for _, y in hits[what]]
        gap = "" if last is None else f", gap to the button on its left {min(xs) - last - 1} px"
        print(f"  {what:9s} {max(xs) - min(xs) + 1} px wide (x {min(xs)}..{max(xs)}), "
              f"{max(ys) - min(ys) + 1} px high (from {min(ys)} to {max(ys)} px above the contents){gap}")
        last = max(xs)
    proc.terminate()
    for manager in reversed(managers):
        manager.terminate()


if __name__ == "__main__":
    main()
