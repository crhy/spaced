#!/usr/bin/python3
import json
import re
import shutil
import subprocess
import threading
import urllib.request

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango


GITHUB_API = "https://api.github.com/repos/crhy/spaced/releases/latest"
APT_RE = re.compile(
    r"^(\S+?)/\S+\s+(\S+)\s+\S+\s+\[upgradable from:\s+(.+)\]$"
)

APP_CSS = b"""
.spaced-page {
    padding: 18px;
}

.spaced-card {
    background-color: alpha(@theme_fg_color, 0.045);
    border: 1px solid alpha(@theme_fg_color, 0.14);
    border-radius: 10px;
    padding: 16px;
}

.spaced-status-icon {
    background-color: alpha(@theme_selected_bg_color, 0.16);
    border-radius: 24px;
    padding: 10px;
}

.spaced-title {
    font-size: 18px;
    font-weight: bold;
}

.spaced-subtitle,
.spaced-muted {
    color: alpha(@theme_fg_color, 0.72);
}

.spaced-count {
    background-color: alpha(@theme_selected_bg_color, 0.16);
    border-radius: 12px;
    padding: 3px 10px;
    font-weight: bold;
}

.spaced-update-list {
    background-color: @theme_base_color;
}

.spaced-update-list row {
    border-bottom: 1px solid alpha(@theme_fg_color, 0.10);
    padding: 8px 10px;
}

.spaced-update-list row:last-child {
    border-bottom-width: 0;
}

.spaced-kind {
    color: @theme_selected_bg_color;
    font-size: 10px;
    font-weight: bold;
}

.spaced-primary-action {
    background-color: @theme_selected_bg_color;
    color: @theme_selected_fg_color;
    border-color: shade(@theme_selected_bg_color, 0.82);
    font-weight: bold;
}

.spaced-primary-action:hover {
    background-color: shade(@theme_selected_bg_color, 1.10);
}

.spaced-primary-action:disabled {
    background-color: alpha(@theme_fg_color, 0.08);
    color: alpha(@theme_fg_color, 0.52);
    border-color: alpha(@theme_fg_color, 0.18);
}

.spaced-action {
    min-height: 30px;
    padding: 3px 12px;
}

.spaced-progress {
    min-height: 12px;
}

.spaced-progress trough,
.spaced-progress progress {
    min-height: 12px;
    border-radius: 6px;
}

.spaced-step-done {
    color: @theme_selected_bg_color;
}

.spaced-step-active {
    font-weight: bold;
}

.spaced-log {
    background-color: shade(@theme_base_color, 0.86);
    color: @theme_text_color;
    font-family: monospace;
    padding: 10px;
}

expander > title {
    padding: 8px 0;
}
"""


def version_key(version):
    numbers = re.findall(r"\d+", version or "0")
    return tuple(int(number) for number in numbers[:4])


def read_installed_version():
    try:
        with open("/etc/os-release", encoding="utf-8") as source:
            for line in source:
                if line.startswith("VERSION_ID="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return None


def run_capture(command, timeout=60):
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(detail or f"{' '.join(command)} exited with status {result.returncode}")
    return result.stdout


def enumerate_apt():
    output = run_capture(["apt", "list", "--upgradable"])
    items = []
    for line in output.splitlines():
        match = APT_RE.match(line.strip())
        if match:
            items.append(
                {
                    "kind": "apt",
                    "name": match.group(1),
                    "cur": match.group(3),
                    "new": match.group(2),
                }
            )
    return sorted(items, key=lambda item: item["name"].casefold())


def enumerate_flatpak():
    if not shutil.which("flatpak"):
        return []

    listed = run_capture(
        ["flatpak", "list", "--app", "--columns=application,installation,ref"]
    )
    updates = run_capture(["flatpak", "remote-ls", "--updates", "--columns=ref"])
    names = run_capture(["flatpak", "list", "--app", "--columns=application,name"])

    update_refs = {
        line.split()[0]
        for line in updates.splitlines()
        if line.strip().startswith("app/")
    }
    name_map = {}
    for line in names.splitlines():
        parts = line.split("\t", 1)
        if len(parts) == 2:
            name_map[parts[0]] = parts[1]

    items = []
    for line in listed.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        app_id, scope, ref = parts[:3]
        if f"app/{ref}" not in update_refs:
            continue
        items.append(
            {
                "kind": "flatpak",
                "name": app_id,
                "ref": ref,
                "scope": scope,
                "display": name_map.get(app_id, app_id),
            }
        )
    return sorted(items, key=lambda item: item["display"].casefold())


def add_style(widget, *classes):
    context = widget.get_style_context()
    for css_class in classes:
        context.add_class(css_class)
    return widget


def make_label(text="", css_class=None, wrap=False):
    label = Gtk.Label(label=text, xalign=0)
    label.set_line_wrap(wrap)
    label.set_selectable(False)
    if css_class:
        add_style(label, css_class)
    return label


def make_scroller(child, min_height=0):
    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scroller.set_overlay_scrolling(False)
    scroller.set_hexpand(True)
    scroller.set_vexpand(True)
    if min_height:
        scroller.set_min_content_height(min_height)
    scroller.add(child)
    return scroller


class UpdateRow(Gtk.ListBoxRow):
    def __init__(self, item, changed_callback):
        super().__init__()
        self.item = item
        self.check = Gtk.CheckButton()
        self.check.set_valign(Gtk.Align.CENTER)
        self.check.connect("toggled", changed_callback)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        if item["kind"] == "apt":
            title = item["name"]
            detail = f'{item["cur"]}  →  {item["new"]}'
            kind = "SYSTEM PACKAGE"
        else:
            title = item["display"]
            detail = f'{item["name"]} · {item["scope"]} installation'
            kind = "FLATPAK APP"

        body.pack_start(make_label(kind, "spaced-kind"), False, False, 0)
        title_label = make_label(title)
        title_label.set_ellipsize(Pango.EllipsizeMode.END)
        body.pack_start(title_label, False, False, 0)
        detail_label = make_label(detail, "spaced-muted")
        detail_label.set_ellipsize(Pango.EllipsizeMode.END)
        body.pack_start(detail_label, False, False, 0)

        row = Gtk.Box(spacing=10)
        row.pack_start(self.check, False, False, 0)
        row.pack_start(body, True, True, 0)
        self.add(row)

    def get_active(self):
        return self.check.get_active()

    def set_active(self, active):
        self.check.set_active(active)


class StepRow(Gtk.Box):
    def __init__(self, title):
        super().__init__(spacing=10)
        self.state = "pending"
        self.icon = Gtk.Image.new_from_icon_name(
            "radio-symbolic", Gtk.IconSize.BUTTON
        )
        self.title = make_label(title, "spaced-muted")
        self.pack_start(self.icon, False, False, 0)
        self.pack_start(self.title, True, True, 0)

    def set_state(self, state):
        self.state = state
        context = self.title.get_style_context()
        context.remove_class("spaced-step-done")
        context.remove_class("spaced-step-active")
        if state == "done":
            self.icon.set_from_icon_name("emblem-ok-symbolic", Gtk.IconSize.BUTTON)
            context.add_class("spaced-step-done")
        elif state == "active":
            self.icon.set_from_icon_name("content-loading-symbolic", Gtk.IconSize.BUTTON)
            context.add_class("spaced-step-active")
        elif state == "error":
            self.icon.set_from_icon_name("dialog-error-symbolic", Gtk.IconSize.BUTTON)
            context.add_class("error")
        else:
            self.icon.set_from_icon_name("radio-symbolic", Gtk.IconSize.BUTTON)


class LogPanel(Gtk.Expander):
    def __init__(self):
        super().__init__(label="Technical details")
        self.set_expanded(False)
        self.view = add_style(Gtk.TextView(), "spaced-log")
        self.view.set_editable(False)
        self.view.set_cursor_visible(False)
        self.view.set_monospace(True)
        self.view.set_wrap_mode(Gtk.WrapMode.NONE)
        self.buffer = self.view.get_buffer()
        self.add(make_scroller(self.view, min_height=180))

    def clear(self):
        self.buffer.set_text("")

    def append(self, text):
        end = self.buffer.get_end_iter()
        self.buffer.insert(end, f"{text}\n")
        self.view.scroll_to_iter(self.buffer.get_end_iter(), 0, False, 0, 0)


class App(Gtk.Window):
    def __init__(self):
        super().__init__(title="Spaced Update")
        self.set_default_size(900, 680)
        self.set_size_request(720, 540)
        self._apt_rows = []
        self._fp_rows = []

        provider = Gtk.CssProvider()
        provider.load_from_data(APP_CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.set_title("Spaced Update")
        header.set_subtitle("System and application updates")
        refresh = Gtk.Button.new_from_icon_name(
            "view-refresh-symbolic", Gtk.IconSize.BUTTON
        )
        refresh.set_tooltip_text("Check for updates")
        refresh.connect("clicked", self.do_check)
        header.pack_end(refresh)
        self.header_refresh = refresh
        self.set_titlebar(header)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)

        self.tabs = Gtk.Stack()
        self.tabs.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        switcher = Gtk.StackSwitcher(stack=self.tabs)
        switcher.set_halign(Gtk.Align.CENTER)
        switcher.set_margin_top(10)
        switcher.set_margin_bottom(4)
        root.pack_start(switcher, False, False, 0)
        root.pack_start(self.tabs, True, True, 0)

        self.tabs.add_titled(self._build_updates_page(), "updates", "Updates")
        self.os_tab = OsUpdateTab(self)
        self.tabs.add_titled(self.os_tab, "os", "OS Release")

        self.connect("destroy", Gtk.main_quit)

    def _build_updates_page(self):
        page = add_style(
            Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14), "spaced-page"
        )

        self.status_icon = add_style(
            Gtk.Image.new_from_icon_name(
                "software-update-available-symbolic", Gtk.IconSize.DIALOG
            ),
            "spaced-status-icon",
        )
        status_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.status_title = make_label("Ready when you are", "spaced-title")
        self.status = make_label(
            "Check for updates to review system packages and Flatpak apps.",
            "spaced-subtitle",
            wrap=True,
        )
        status_text.pack_start(self.status_title, False, False, 0)
        status_text.pack_start(self.status, False, False, 0)
        status_card = add_style(Gtk.Box(spacing=14), "spaced-card")
        status_card.pack_start(self.status_icon, False, False, 0)
        status_card.pack_start(status_text, True, True, 0)
        page.pack_start(status_card, False, False, 0)

        controls = Gtk.Box(spacing=10)
        self.selectall = Gtk.CheckButton(label="Select all")
        self.selectall.set_sensitive(False)
        self.selectall.connect("toggled", self.on_select_all)
        controls.pack_start(self.selectall, False, False, 0)
        self.selection_count = add_style(make_label("0 selected"), "spaced-count")
        controls.pack_start(self.selection_count, False, False, 0)
        controls.pack_end(make_label("Choose exactly what to install", "spaced-muted"), False, False, 0)
        page.pack_start(controls, False, False, 0)

        self.content_stack = Gtk.Stack()
        self.content_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.content_stack.set_hexpand(True)
        self.content_stack.set_vexpand(True)

        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        empty.set_halign(Gtk.Align.CENTER)
        empty.set_valign(Gtk.Align.CENTER)
        self.empty_spinner = Gtk.Spinner()
        self.empty_spinner.set_no_show_all(True)
        self.empty_spinner.hide()
        self.empty_icon = Gtk.Image.new_from_icon_name(
            "software-update-available-symbolic", Gtk.IconSize.DIALOG
        )
        self.empty_title = make_label("No update check yet", "spaced-title")
        self.empty_detail = make_label(
            "Use Check for Updates to load the latest package information.",
            "spaced-muted",
            wrap=True,
        )
        self.empty_title.set_xalign(0.5)
        self.empty_detail.set_xalign(0.5)
        empty.pack_start(self.empty_spinner, False, False, 0)
        empty.pack_start(self.empty_icon, False, False, 0)
        empty.pack_start(self.empty_title, False, False, 0)
        empty.pack_start(self.empty_detail, False, False, 0)
        self.content_stack.add_named(empty, "empty")

        self.listbox = add_style(Gtk.ListBox(), "spaced-update-list")
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        list_scroll = make_scroller(self.listbox)
        add_style(list_scroll, "spaced-card")
        self.content_stack.add_named(list_scroll, "list")

        self.progress_page = self._build_progress_page()
        self.content_stack.add_named(self.progress_page, "progress")
        self.content_stack.set_visible_child_name("empty")
        page.pack_start(self.content_stack, True, True, 0)

        actions = Gtk.Box(spacing=8)
        self.checkbtn = add_style(Gtk.Button(label="Check for Updates"), "spaced-action")
        self.checkbtn.connect("clicked", self.do_check)
        self.runbtn = add_style(
            Gtk.Button(label="Install Selected"),
            "spaced-action",
            "spaced-primary-action",
        )
        self.runbtn.set_sensitive(False)
        self.runbtn.connect("clicked", self.do_install)
        actions.pack_end(self.runbtn, False, False, 0)
        actions.pack_end(self.checkbtn, False, False, 0)
        page.pack_start(actions, False, False, 0)
        return page

    def _build_progress_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        heading = make_label("Installing updates", "spaced-title")
        self.pstatus = make_label("Preparing…", "spaced-subtitle", wrap=True)
        page.pack_start(heading, False, False, 0)
        page.pack_start(self.pstatus, False, False, 0)

        self.pbar = add_style(Gtk.ProgressBar(), "spaced-progress")
        self.pbar.set_show_text(True)
        page.pack_start(self.pbar, False, False, 0)

        steps_box = add_style(
            Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10), "spaced-card"
        )
        self.steps = [
            StepRow("Prepare and verify"),
            StepRow("Update system packages"),
            StepRow("Update Flatpak applications"),
            StepRow("Finish and clean up"),
        ]
        for step in self.steps:
            steps_box.pack_start(step, False, False, 0)
        page.pack_start(steps_box, False, False, 0)

        self.details = LogPanel()
        page.pack_start(self.details, True, True, 0)

        self.back_button = add_style(
            Gtk.Button(label="Back to Update List"), "spaced-action"
        )
        self.back_button.set_no_show_all(True)
        self.back_button.connect(
            "clicked", lambda *_: self.content_stack.set_visible_child_name("list")
        )
        page.pack_end(self.back_button, False, False, 0)
        return page

    def _set_status(self, icon_name, title, detail):
        self.status_icon.set_from_icon_name(icon_name, Gtk.IconSize.DIALOG)
        self.status_title.set_text(title)
        self.status.set_text(detail)

    def logline(self, text):
        self.details.append(text)

    def setstep(self, percent, message):
        percent = max(0, min(100, percent))
        self.pstatus.set_text(message)
        self.pbar.set_fraction(percent / 100)
        self.pbar.set_text(f"{percent}%")

        thresholds = (10, 35, 70, 92)
        if percent >= 100:
            states = ("done",) * 4
        else:
            active = max(
                index for index, threshold in enumerate(thresholds) if percent >= threshold
            ) if percent >= thresholds[0] else 0
            states = tuple(
                "done" if index < active else "active" if index == active else "pending"
                for index in range(4)
            )
        for step, state in zip(self.steps, states):
            step.set_state(state)

    def show_error(self, message):
        self.pstatus.set_text(message)
        for step in self.steps:
            if step.state == "active":
                step.set_state("error")
                break
        self.details.set_expanded(True)

    def do_check(self, *_):
        self.checkbtn.set_sensitive(False)
        self.header_refresh.set_sensitive(False)
        self.selectall.set_active(False)
        self.selectall.set_sensitive(False)
        self.runbtn.set_sensitive(False)
        self._clear_list()
        self._set_status(
            "content-loading-symbolic",
            "Checking for updates",
            "Reading APT and Flathub metadata…",
        )
        self.empty_icon.hide()
        self.empty_spinner.show()
        self.empty_spinner.start()
        self.empty_title.set_text("Checking repositories")
        self.empty_detail.set_text("This usually takes only a moment.")
        self.content_stack.set_visible_child_name("empty")
        threading.Thread(target=self._check_worker, daemon=True).start()

    def _clear_list(self):
        for row in self.listbox.get_children():
            self.listbox.remove(row)
        self._apt_rows = []
        self._fp_rows = []
        self.selection_count.set_text("0 selected")

    def _check_worker(self):
        try:
            apt = enumerate_apt()
            flatpak = enumerate_flatpak()
            GLib.idle_add(self._check_done, apt, flatpak, None)
        except Exception as error:
            GLib.idle_add(self._check_done, [], [], error)

    def _check_done(self, apt, flatpak, error):
        self.checkbtn.set_sensitive(True)
        self.header_refresh.set_sensitive(True)
        self.empty_spinner.stop()
        self.empty_spinner.hide()
        self.empty_icon.show()
        if error:
            self._set_status(
                "dialog-warning-symbolic",
                "Could not check for updates",
                "Open Technical details after an install attempt, or check your connection and try again.",
            )
            self.empty_icon.set_from_icon_name("dialog-warning-symbolic", Gtk.IconSize.DIALOG)
            self.empty_title.set_text("Update check failed")
            self.empty_detail.set_text(str(error))
            self.content_stack.set_visible_child_name("empty")
            return

        for item in apt:
            row = UpdateRow(item, self.on_selection_changed)
            self._apt_rows.append(row)
            self.listbox.add(row)
        for item in flatpak:
            row = UpdateRow(item, self.on_selection_changed)
            self._fp_rows.append(row)
            self.listbox.add(row)

        total = len(apt) + len(flatpak)
        if not total:
            self._set_status(
                "emblem-ok-symbolic",
                "You’re up to date",
                "No system package or Flatpak application updates are available.",
            )
            self.empty_icon.set_from_icon_name("emblem-ok-symbolic", Gtk.IconSize.DIALOG)
            self.empty_title.set_text("Everything is current")
            self.empty_detail.set_text("Check again whenever you like.")
            self.content_stack.set_visible_child_name("empty")
            return

        self.listbox.show_all()
        self._set_status(
            "software-update-available-symbolic",
            f"{total} update{'s' if total != 1 else ''} available",
            f"{len(apt)} system package{'s' if len(apt) != 1 else ''} and "
            f"{len(flatpak)} Flatpak app{'s' if len(flatpak) != 1 else ''}.",
        )
        self.selectall.set_sensitive(True)
        self.content_stack.set_visible_child_name("list")

    def on_select_all(self, *_):
        active = self.selectall.get_active()
        for row in self._apt_rows + self._fp_rows:
            row.set_active(active)
        self.on_selection_changed()

    def on_selection_changed(self, *_):
        count = len(self.selected_items())
        self.selection_count.set_text(f"{count} selected")
        self.runbtn.set_sensitive(count > 0)

    def selected_items(self):
        return [
            row.item
            for row in self._apt_rows + self._fp_rows
            if row.get_active()
        ]

    def do_install(self, *_):
        items = self.selected_items()
        if not items:
            return
        self.runbtn.set_sensitive(False)
        self.selectall.set_sensitive(False)
        self.checkbtn.set_sensitive(False)
        self.header_refresh.set_sensitive(False)
        self.details.clear()
        self.details.set_expanded(False)
        self.back_button.hide()
        self.setstep(0, "Preparing selected updates…")
        self.content_stack.set_visible_child_name("progress")
        threading.Thread(
            target=self._install_worker, args=(items,), daemon=True
        ).start()

    def _install_worker(self, items):
        apt = [item["name"] for item in items if item["kind"] == "apt"]
        flatpak_user = [
            item["ref"]
            for item in items
            if item["kind"] == "flatpak" and item["scope"] == "user"
        ]
        flatpak_system = [
            item["ref"]
            for item in items
            if item["kind"] == "flatpak" and item["scope"] == "system"
        ]
        jobs = []
        if apt:
            jobs.append(("apt", apt))
        if flatpak_user:
            jobs.append(("flatpak-user", flatpak_user))
        if flatpak_system:
            jobs.append(("flatpak-system", flatpak_system))

        try:
            GLib.idle_add(self.setstep, 5, "Preparing selected updates…")
            for index, (kind, values) in enumerate(jobs):
                start = 10 + round(index * 78 / len(jobs))
                end = 10 + round((index + 1) * 78 / len(jobs))
                if kind == "apt":
                    GLib.idle_add(
                        self.logline,
                        f"Installing {len(values)} selected system package(s)",
                    )
                    status = self.run_cmd(
                        [
                            "pkexec",
                            "/usr/lib/spaced-linux/spaced-update-helper",
                            "apt-install",
                        ]
                        + values,
                        self.logline,
                        self.setstep,
                        (start, end),
                    )
                elif kind == "flatpak-user":
                    GLib.idle_add(
                        self.setstep, start, "Updating your Flatpak applications…"
                    )
                    status = self.run_flatpak_update("--user", values)
                    GLib.idle_add(self.setstep, end, "Flatpak applications updated")
                else:
                    status = self.run_cmd(
                        [
                            "pkexec",
                            "/usr/lib/spaced-linux/spaced-update-helper",
                            "flatpak-update",
                            "--system",
                        ]
                        + values,
                        self.logline,
                        self.setstep,
                        (start, end),
                    )
                if status:
                    raise RuntimeError(f"Update command exited with status {status}")

            GLib.idle_add(self.setstep, 94, "Finishing and refreshing menus…")
            GLib.idle_add(self.setstep, 100, "Updates installed successfully")
            GLib.idle_add(self.logline, "Finished successfully.")
            GLib.idle_add(
                self._set_status,
                "emblem-ok-symbolic",
                "Updates installed",
                "Your selected updates completed successfully.",
            )
        except Exception as error:
            GLib.idle_add(self.logline, f"ERROR: {error}")
            GLib.idle_add(self.show_error, "The update needs attention")
            GLib.idle_add(
                self._set_status,
                "dialog-error-symbolic",
                "Update failed",
                "Expand Technical details for the command output.",
            )
        finally:
            GLib.idle_add(self.back_button.show)
            GLib.idle_add(self.selectall.set_sensitive, True)
            GLib.idle_add(self.checkbtn.set_sensitive, True)
            GLib.idle_add(self.header_refresh.set_sensitive, True)

    def run_flatpak_update(self, scope, refs):
        process = subprocess.Popen(
            ["flatpak", "update", "-y", scope] + refs,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in process.stdout:
            GLib.idle_add(self.logline, line.rstrip())
        return process.wait()

    def run_cmd(self, command, log_callback, step_callback, progress_range=(0, 100)):
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        start, end = progress_range
        for line in process.stdout:
            line = line.rstrip()
            match = re.match(r"SPACED_STEP:(\d+):(.*)", line)
            if match:
                source_percent = int(match.group(1))
                mapped = start + round((end - start) * source_percent / 100)
                GLib.idle_add(step_callback, mapped, match.group(2))
            else:
                GLib.idle_add(log_callback, line)
        return process.wait()

    def do_os_update(self, *_):
        tab = self.os_tab
        tab.updatebtn.set_sensitive(False)
        tab.details.clear()
        tab.details.set_expanded(False)
        tab.setstep(2, "Preparing the full system update…")
        threading.Thread(target=self._os_update_worker, daemon=True).start()

    def _os_update_worker(self):
        tab = self.os_tab
        try:
            status = self.run_cmd(
                ["pkexec", "/usr/lib/spaced-linux/spaced-update-helper"],
                tab.logline,
                tab.setstep,
            )
            if status:
                raise RuntimeError(
                    f"System update helper exited with status {status}"
                )
            GLib.idle_add(tab.setstep, 100, "System update complete")
            GLib.idle_add(
                tab.set_message,
                "emblem-ok-symbolic",
                "Your system is updated",
                "A reboot is recommended to finish applying kernel and system changes.",
            )
            GLib.idle_add(tab.logline, "Finished successfully.")
        except Exception as error:
            GLib.idle_add(tab.logline, f"ERROR: {error}")
            GLib.idle_add(tab.details.set_expanded, True)
            GLib.idle_add(
                tab.set_message,
                "dialog-error-symbolic",
                "System update failed",
                "Review Technical details, then try again when the problem is resolved.",
            )
        finally:
            GLib.idle_add(tab.updatebtn.set_sensitive, True)


class OsUpdateTab(Gtk.Box):
    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        add_style(self, "spaced-page")
        self.app = app
        self.installed = read_installed_version()

        hero = add_style(Gtk.Box(spacing=14), "spaced-card")
        self.message_icon = add_style(
            Gtk.Image.new_from_icon_name(
                "computer-symbolic", Gtk.IconSize.DIALOG
            ),
            "spaced-status-icon",
        )
        message_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.message_title = make_label("Spaced Linux release status", "spaced-title")
        self.message = make_label(
            "Check the published release and update through your configured repositories.",
            "spaced-subtitle",
            wrap=True,
        )
        message_box.pack_start(self.message_title, False, False, 0)
        message_box.pack_start(self.message, False, False, 0)
        hero.pack_start(self.message_icon, False, False, 0)
        hero.pack_start(message_box, True, True, 0)
        self.pack_start(hero, False, False, 0)

        versions = add_style(Gtk.Box(spacing=24), "spaced-card")
        installed_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        installed_box.pack_start(make_label("INSTALLED", "spaced-kind"), False, False, 0)
        self.inst = make_label(self.installed or "Unknown", "spaced-title")
        installed_box.pack_start(self.inst, False, False, 0)
        latest_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        latest_box.pack_start(make_label("LATEST RELEASE", "spaced-kind"), False, False, 0)
        self.latest = make_label("Not checked", "spaced-title")
        latest_box.pack_start(self.latest, False, False, 0)
        versions.pack_start(installed_box, True, True, 0)
        versions.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 0)
        versions.pack_start(latest_box, True, True, 0)
        self.pack_start(versions, False, False, 0)

        self.progress = add_style(Gtk.ProgressBar(), "spaced-progress")
        self.progress.set_show_text(True)
        self.progress.hide()
        self.progress.set_no_show_all(True)
        self.pack_start(self.progress, False, False, 0)

        self.details = LogPanel()
        self.pack_start(self.details, True, True, 0)

        actions = Gtk.Box(spacing=8)
        self.checkbtn = add_style(Gtk.Button(label="Check Release"), "spaced-action")
        self.checkbtn.connect("clicked", self.check)
        self.updatebtn = add_style(
            Gtk.Button(label="Update System"),
            "spaced-action",
            "spaced-primary-action",
        )
        self.updatebtn.set_sensitive(False)
        self.updatebtn.connect("clicked", self.app.do_os_update)
        actions.pack_end(self.updatebtn, False, False, 0)
        actions.pack_end(self.checkbtn, False, False, 0)
        self.pack_end(actions, False, False, 0)

    def set_message(self, icon, title, detail):
        self.message_icon.set_from_icon_name(icon, Gtk.IconSize.DIALOG)
        self.message_title.set_text(title)
        self.message.set_text(detail)

    def logline(self, text):
        self.details.append(text)

    def setstep(self, percent, message):
        self.progress.show()
        self.progress.set_fraction(max(0, min(100, percent)) / 100)
        self.progress.set_text(f"{percent}% — {message}")

    def check(self, *_):
        self.checkbtn.set_sensitive(False)
        self.set_message(
            "content-loading-symbolic",
            "Checking the release feed",
            "Comparing the installed system with the latest published release…",
        )
        threading.Thread(target=self._check_worker, daemon=True).start()

    def _check_worker(self):
        try:
            request = urllib.request.Request(
                GITHUB_API,
                headers={
                    "User-Agent": "spaced-update",
                    "Accept": "application/vnd.github+json",
                },
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                release = json.load(response)
            if release.get("draft") or not release.get("tag_name"):
                raise RuntimeError("No published release was returned.")
            GLib.idle_add(self._check_done, release["tag_name"], None)
        except Exception as error:
            GLib.idle_add(self._check_done, None, error)

    def _check_done(self, latest, error):
        self.checkbtn.set_sensitive(True)
        if error:
            self.set_message(
                "dialog-warning-symbolic",
                "Could not reach the release feed",
                "Check your connection and try again.",
            )
            self.logline(f"ERROR: {error}")
            self.details.set_expanded(True)
            return

        self.latest.set_text(latest)
        if self.installed and version_key(latest) > version_key(self.installed):
            self.set_message(
                "software-update-available-symbolic",
                "A newer release is available",
                "Spaced Linux is rolling; the update comes from your package repositories, not an ISO download.",
            )
            self.updatebtn.set_sensitive(True)
            self.logline(f"Newer version available: {latest}")
        elif self.installed:
            self.set_message(
                "emblem-ok-symbolic",
                "Your release is current",
                "Your configured repositories already track the latest Spaced Linux release.",
            )
            self.updatebtn.set_sensitive(True)
        else:
            self.set_message(
                "dialog-information-symbolic",
                "Installed version is unknown",
                "You can still safely update from the configured repositories.",
            )
            self.updatebtn.set_sensitive(True)


if __name__ == "__main__":
    application = App()
    application.show_all()
    application.os_tab.progress.hide()
    Gtk.main()
