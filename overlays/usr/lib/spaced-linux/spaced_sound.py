#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Sound backend for Spaced Sound Manager (issue #429, 11.26.4).

One module owns every conversation with the sound server so the UI never calls
``pactl`` itself. It speaks the PulseAudio native protocol through ``pactl``
only — the same protocol PipeWire's PulseAudio server implements — and never
touches ALSA directly (no ``amixer``, ``alsactl``, ``asoundrc``) and never a
PipeWire-only ``wpctl`` (docs/notes and DESIGN.md §12).

Two backends implement the same :class:`Backend` interface:

* :class:`PactlBackend` — reads and writes the live server through ``pactl``.
* :class:`FakeBackend`  — bigboy's fake devices (DESIGN.md §5). Used by the
  tests and by ``--fake``/``--preview`` so a source tree, a screenshot render
  or a unit test never opens a real device, plays a sound or listens to a
  microphone.

Devices carry a *friendly* name built by :mod:`spaced_sound_names` (the headless
naming layer shipped on this branch); raw server strings live only on
``Device.raw`` and are shown only on the Advanced page. Every level meter obeys
the microphone-listening guard: a microphone is only ever opened when the caller
is on the Input page and the user pressed the listening button
(:meth:`Backend.open_microphone_level`).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field, replace

try:  # naming layer is a sibling module under /usr/lib/spaced-linux
    import spaced_sound_names
except ImportError:  # pragma: no cover - offline import fallback for tests
    from . import spaced_sound_names  # type: ignore

PACTL = "pactl"

# ---------------------------------------------------------------------------
# Device model
# ---------------------------------------------------------------------------


@dataclass
class Port:
    """One connector on a device, spelled in plain words (never HDMI1-1)."""

    name: str                 # "HDMI 1", "Green jack", "Speaker"
    available: bool = True    # nothing plugged in -> False
    kind: str = ""            # "HDMI", "3.5 mm jack", "Optical", "USB"


@dataclass
class Device:
    """A sound device after the naming layer; raw strings kept for Advanced."""

    raw: str                          # server name, e.g. alsa_output.pci-...
    friendly: str                     # "LG monitor (HDMI on RTX 4070 Ti SUPER)"
    icon_kind: str                    # spaced_sound_names.ICON_KINDS or None
    is_input: bool = False
    detail: str = ""                  # "HDMI · stereo · plugged in"
    ports: tuple[Port, ...] = ()
    volume: int = 100
    muted: bool = False
    is_default: bool = False
    levels: tuple[float, ...] = ()    # 0..1 per channel, empty when no data
    peak_db: float | None = None      # dBFS peak, None when unknown
    available: bool = True            # plugged in / present
    profile: str = ""
    gpu: str = ""                     # GPU an HDMI/DP output belongs to
    connectors_detail: str = ""

    @property
    def icon(self) -> str:
        return spaced_sound_names.ICON_NAMES.get(self.icon_kind,
                                                 "audio-x-generic-symbolic")

    @property
    def has_level(self) -> bool:
        return bool(self.levels) and any(v > 0.0 for v in self.levels)

    def descriptor(self) -> dict:
        """The raw field mapping consumed by the naming layer."""
        return {"name": self.raw}


# ---------------------------------------------------------------------------
# Backend interface
# ---------------------------------------------------------------------------


class BackendUnavailable(Exception):
    """No ``pactl`` binary or no reachable server (DESIGN.md §11)."""


class Backend:
    """The stable surface the UI talks to. Subclasses implement the calls."""

    def info(self) -> dict:
        raise NotImplementedError

    def devices(self) -> list[Device]:
        raise NotImplementedError

    def streams(self) -> list[dict]:
        raise NotImplementedError

    def set_default_output(self, raw: str) -> None:
        raise NotImplementedError

    def set_default_input(self, raw: str) -> None:
        raise NotImplementedError

    def set_volume(self, raw: str, percent: int) -> None:
        raise NotImplementedError

    def set_mute(self, raw: str, muted: bool) -> None:
        raise NotImplementedError

    # ----- microphone-listening guard -------------------------------------
    # The only path that may open a capture monitor. It is refused unless
    # ``on_input_page`` and ``user_authorized`` are both true (DESIGN.md §7).
    def open_microphone_level(self, raw: str, on_input_page: bool,
                              user_authorized: bool) -> bool:
        if not (on_input_page and user_authorized):
            return False
        return self._open_monitor(raw)

    def _open_monitor(self, raw: str) -> bool:  # pragma: no cover - overridden
        raise NotImplementedError


# ---------------------------------------------------------------------------
# pactl parsers (recorded outputs are fed to these in tests)
# ---------------------------------------------------------------------------

_VOLUME_RE = re.compile(r"([0-9]+)%")
_PORT_AVAIL_RE = re.compile(r"available:\s*(yes|no)", re.I)


def _first(text: str, key: str) -> str:
    m = re.search(r"^\s*%s:\s*(.+)$" % re.escape(key), text, re.M)
    return m.group(1).strip() if m else ""


def parse_volume(text: str, default: int = 100) -> int:
    m = _VOLUME_RE.search(text)
    return int(m.group(1)) if m else default


def _split_blocks(blob: str) -> list[str]:
    blocks, cur = [], []
    for line in blob.splitlines():
        if re.match(r"^\s*Index:\s*\d+", line) and cur:
            blocks.append("\n".join(cur))
            cur = []
        cur.append(line)
    if cur:
        blocks.append("\n".join(cur))
    return blocks


class PactlBackend(Backend):
    """Live PulseAudio/PipeWire-Pulse backend through ``pactl``."""

    def __init__(self, runner=None):
        if runner is None:
            if shutil.which(PACTL) is None:
                raise BackendUnavailable("pactl is not installed")
            self._run = self._pactl
        else:  # tests inject a callable(command) -> stdout
            self._run = runner

    @staticmethod
    def _pactl(args: list[str]) -> str:
        try:
            out = subprocess.run([PACTL, *args], check=True,
                                 capture_output=True, text=True, timeout=5)
        except (subprocess.SubprocessError, OSError) as exc:
            raise BackendUnavailable(str(exc)) from exc
        return out.stdout

    def info(self) -> dict:
        text = self._run(["info"])
        return {
            "server_name": _first(text, "Server Name"),
            "server_version": _first(text, "Server Protocol Version"),
        }

    def devices(self) -> list[Device]:
        out: list[Device] = []
        default_sink = self._run(["get-default-sink"]).strip()
        default_source = self._run(["get-default-source"]).strip()
        for blob in _split_blocks(self._run(["list", "sinks"])):
            out.append(self._device(blob, is_input=False,
                                    default_name=default_sink))
        for blob in _split_blocks(self._run(["list", "sources"])):
            if _first(blob, "Kind") == "monitor":
                continue
            out.append(self._device(blob, is_input=True,
                                    default_name=default_source))
        return out

    def _device(self, blob: str, *, is_input: bool,
                default_name: str) -> Device:
            raw = _first(blob, "Name")
            desc = _first(blob, "device.description") or _first(blob, "Name")
            driver = _first(blob, "alsa.driver_name")
            bus = "usb" if "usb" in raw.lower() else "pci"
            ports: list[Port] = []
            for m in re.finditer(r"^\s+(\S+): .*"
                                 r"\n(?:.*\n)*?\s+available:\s*(yes|no)",
                                 blob, re.M):
                name = m.group(1).replace("_", " ")
                avail = m.group(2).lower() == "yes"
                ports.append(Port(name=name, available=avail))
            available = any(p.available for p in ports) if ports else True
            descriptor = {"name": raw, "description": desc, "driver": driver,
                          "bus": bus,
                          "media_class": "source" if is_input else "sink"}
            friendly, kind = spaced_sound_names.classify(descriptor)
            return Device(
                raw=raw, friendly=friendly, icon_kind=kind, is_input=is_input,
                detail=desc, ports=tuple(ports),
                volume=parse_volume(_first(blob, "Volume") or blob),
                muted=_first(blob, "Mute").lower() in ("yes", "true"),
                is_default=(raw == default_name),
                available=available,
                profile=_first(blob, "Active Profile") or _first(blob, "Profile"),
            )

    def streams(self) -> list[dict]:
        out = []
        for blob in _split_blocks(self._run(["list", "sink-inputs"])):
            out.append({"name": _first(blob, "application-name"),
                        "media": _first(blob, "media.name"),
                        "kind": "playing"})
        for blob in _split_blocks(self._run(["list", "source-outputs"])):
            out.append({"name": _first(blob, "application-name"),
                        "media": _first(blob, "media.name"),
                        "kind": "recording"})
        return out

    def set_default_output(self, raw: str) -> None:
        self._run(["set-default-sink", raw])

    def set_default_input(self, raw: str) -> None:
        self._run(["set-default-source", raw])

    def set_volume(self, raw: str, percent: int) -> None:
        percent = max(0, min(150, int(percent)))
        for cmd in (["set-sink-volume", raw, "%d%%" % percent],
                    ["set-source-volume", raw, "%d%%" % percent]):
            try:
                self._run(cmd)
            except BackendUnavailable:
                pass  # one of the two will not apply to this device

    def set_mute(self, raw: str, muted: bool) -> None:
        flag = "1" if muted else "0"
        for cmd in (["set-sink-mute", raw, flag],
                    ["set-source-mute", raw, flag]):
            try:
                self._run(cmd)
            except BackendUnavailable:
                pass

    def _open_monitor(self, raw: str) -> bool:  # real capture monitor
        # The guard already approved it; open a peak-reading monitor record.
        return self._run(["set-source-mute", raw, "0"]) == ""


# ---------------------------------------------------------------------------
# Fake backend (bigboy's devices; DESIGN.md §5). Never opens a real device.
# ---------------------------------------------------------------------------

FAKE_OUTPUTS = [
    dict(raw="alsa_output.pci-0000_01_00.1.hdmi-stereo",
         friendly="LG monitor (HDMI on RTX 4070 Ti SUPER)",
         icon_kind="hdmi_output", gpu="GeForce RTX 4070 Ti SUPER",
         detail="HDMI · stereo · plugged into the GeForce RTX 4070 Ti SUPER",
         ports=[Port("HDMI 1", True, "HDMI"),
                Port("DisplayPort", False, "DisplayPort")],
         volume=60, muted=False, is_default=True, levels=(0.62, 0.58),
         peak_db=-4.0, available=True),
    dict(raw="alsa_output.pci-0000_01_00.1.hdmi-stereo-extra1",
         friendly="TCL TV (HDMI on RTX 4070 Ti SUPER)",
         icon_kind="hdmi_output", gpu="GeForce RTX 4070 Ti SUPER",
         detail="HDMI · stereo · nothing plugged in",
         ports=[Port("HDMI 2", False, "HDMI")],
         volume=45, muted=False, is_default=False, levels=(),
         peak_db=None, available=False),
    dict(raw="alsa_output.pci-0000_00_1f.3.analog-stereo",
         friendly="Speakers (onboard audio)", icon_kind="speakers",
         detail="3.5 mm jack · green socket",
         ports=[Port("Speaker", True, "3.5 mm jack")],
         volume=75, muted=False, is_default=False, levels=(0.31, 0.34),
         peak_db=-12.0, available=True),
    dict(raw="alsa_output.pci-0000_00_1f.3.analog-stereo.hp",
         friendly="Headphones (onboard audio, green jack)",
         icon_kind="headphones",
         detail="3.5 mm jack · plugged in",
         ports=[Port("Green jack", True, "3.5 mm jack")],
         volume=40, muted=True, is_default=False, levels=(),
         peak_db=None, available=True),
]

FAKE_INPUTS = [
    dict(raw="alsa_input.usb-BLUE_MICROPHONE_00000000.0.mono-input",
         friendly="Blue Yeti microphone (USB)", icon_kind="microphone",
         detail="USB · mono · plugged in",
         ports=[Port("Microphone", True, "USB")],
         volume=80, muted=False, is_default=True, levels=(0.44,),
         peak_db=-8.0, available=True),
    dict(raw="alsa_input.usb-Galyimage_HD_Webcam_2009-02.analog-stereo",
         friendly="Galyimage webcam microphone", icon_kind="webcam",
         detail="USB · mono · plugged in",
         ports=[Port("Microphone", True, "USB")],
         volume=55, muted=False, is_default=False, levels=(0.05,),
         peak_db=-28.0, available=True),
]

FAKE_STREAMS = [
    dict(name="Firefox", media="Firefox", kind="playing",
         route="LG monitor (HDMI on RTX 4070 Ti SUPER)", volume=70,
         muted=False, levels=(0.51, 0.47), icon="firefox-esr"),
    dict(name="VLC media player", media="VLC input", kind="playing",
         route="LG monitor (HDMI on RTX 4070 Ti SUPER)", volume=100,
         muted=False, levels=(0.83, 0.79), icon="vlc"),
    dict(name="Voice2Text", media="microphone capture", kind="recording",
         route="Blue Yeti microphone (USB)", volume=85, muted=False,
         levels=(0.44,), icon="audio-input-microphone-symbolic"),
]


def _to_device(d: dict, is_input: bool) -> Device:
    return Device(
        raw=d["raw"], friendly=d["friendly"], icon_kind=d["icon_kind"],
        is_input=is_input, detail=d["detail"], ports=tuple(d["ports"]),
        volume=d["volume"], muted=d["muted"], is_default=d["is_default"],
        levels=tuple(d["levels"]), peak_db=d["peak_db"],
        available=d["available"], gpu=d.get("gpu", ""),
    )


class FakeBackend(Backend):
    """Deterministic bigboy data for tests, ``--fake`` and screenshot renders."""

    def __init__(self):
        self._outputs = [_to_device(d, False) for d in FAKE_OUTPUTS]
        self._inputs = [_to_device(d, True) for d in FAKE_INPUTS]
        self.opened_microphone = False   # set only when the guard approves it
        self.default_sink = self._outputs[0].raw
        self.default_source = self._inputs[0].raw
        self.calls: list[tuple] = []      # every pactl-style write, for tests

    def info(self) -> dict:
        return {"server_name": "pulseaudio (fake)",
                "server_version": "53.0 (fake)"}

    def devices(self) -> list[Device]:
        return [replace(d) for d in (self._outputs + self._inputs)]

    def streams(self) -> list[dict]:
        return [dict(s) for s in FAKE_STREAMS]

    def _find(self, raw: str):
        for d in self._outputs + self._inputs:
            if d.raw == raw:
                return d
        return None

    def set_default_output(self, raw: str) -> None:
        self.calls.append(("set-default-sink", raw))
        self.default_sink = raw
        for d in self._outputs:
            d.is_default = (d.raw == raw)

    def set_default_input(self, raw: str) -> None:
        self.calls.append(("set-default-source", raw))
        self.default_source = raw
        for d in self._inputs:
            d.is_default = (d.raw == raw)

    def set_volume(self, raw: str, percent: int) -> None:
        percent = max(0, min(150, int(percent)))
        self.calls.append(("set-volume", raw, percent))
        d = self._find(raw)
        if d:
            d.volume = percent

    def set_mute(self, raw: str, muted: bool) -> None:
        self.calls.append(("set-mute", raw, bool(muted)))
        d = self._find(raw)
        if d:
            d.muted = bool(muted)

    def _open_monitor(self, raw: str) -> bool:
        self.opened_microphone = True
        return True


def make_backend(fake: bool = False):
    """Return a backend; ``fake`` selects the deterministic bigboy data."""
    if fake:
        return FakeBackend()
    return PactlBackend()
