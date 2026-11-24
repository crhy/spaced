"""Friendly per-kind names and icon kinds for Spaced Sound Manager (issue #429).

The headless naming layer a future panel consumes: it turns a raw sound-server
device descriptor into a friendly name plus one fixed icon kind, never a raw
server string, and it never invents a fact it was not given. It is pure
(standard library only), imports cleanly with
``PYTHONPATH=overlays/usr/lib/spaced-linux`` and is testable offline — it reads
no system settings, opens no device and plays no sound.

``classify(descriptor)`` accepts a mapping of the stable PulseAudio/PipeWire
fields the sound server already reports, and returns ``(friendly_name,
icon_kind)``. Recognised fields (all optional):

  name / description   raw server name and human string (used only as a fallback)
  media_class          direction: a sink/playback class is an output, a
                       source/record class is an input
  bus                  "usb", "pci" or "platform" (how the card is attached)
  driver               ALSA driver string, e.g. "HD-Audio Generic", "HDA NVidia"
  ports / port         port type tokens, e.g. "analog-output", "headphones",
                       "hdmi", "displayport", "analog-input-mic", "optical"
  gpu                  the GPU an HDMI/DisplayPort audio function belongs to
  monitor              the monitor name read from its EDID (HDMI/DP cards)
  product              USB/udev product model, e.g. "Blue Yeti", "Galyimage"
  connector            connector detail, e.g. "green jack", "HDMI 1"
  onboard              True when the analog card is the motherboard's own audio
  webcam               True when an input is a camera's microphone

icon_kind is one of :data:`ICON_KINDS`; an unrecognised device falls back to
``None`` (the panel then renders the generic icon) with the raw name kept. The
port/media fields always win over the driver string when a port type is
present, so "HD-Audio Generic" names as speakers/headphones by its port while
"HDA NVidia" names as an HDMI output carrying the GPU it drives.
"""

ICON_KINDS = ("speakers", "headphones", "microphone", "webcam",
              "hdmi_output", "digital")

# DESIGN.md §4: each kind resolves to one symbolic icon (the desktop theme
# tints it; nothing is chosen by a vendor colour). ``None`` falls back to the
# generic icon, which is the point of #429 — no device renders as a PCI card.
ICON_NAMES = {
    "speakers": "audio-speakers-symbolic",
    "headphones": "audio-headphones-symbolic",
    "microphone": "audio-input-microphone-symbolic",
    "webcam": "audio-input-microphone-symbolic",
    "hdmi_output": "video-display-symbolic",
    "digital": "audio-optical-symbolic",
    None: "audio-x-generic-symbolic",
}

_HDMI_TOKENS = ("hdmi", "displayport", "dp", "display-port")
_DIGITAL_TOKENS = ("optical", "iec958", "spdif", "digital")
_HEADPHONE_TOKENS = ("headphone", "headset", "hp")
_SPEAKER_TOKENS = ("analog-output", "analog-out", "speakers", "line-out",
                   "lineout")
_MIC_TOKENS = ("mic", "microphone", "analog-input", "input")
_WEBCAM_HINTS = ("webcam", "camera", "web cam")


def _tokens(descriptor):
    """All port-type tokens for the device, lower-cased and split."""
    ports = descriptor.get("ports")
    if ports is None and descriptor.get("port") is not None:
        ports = [descriptor.get("port")]
    if isinstance(ports, str):
        ports = ports.replace(",", " ").split()
    tokens = []
    for port in ports or ():
        if not port:
            continue
        for part in str(port).replace(",", " ").replace("/", " ").split():
            tokens.append(part.lower())
    return tokens


def _is_input(descriptor, tokens):
    media_class = str(descriptor.get("media_class", "")).lower()
    if any(word in media_class for word in ("source", "record", "capture",
                                            "input")):
        return True
    return bool(set(tokens) & {t for t in tokens if t in _MIC_TOKENS})


def _is_webcam(descriptor, tokens):
    if descriptor.get("webcam"):
        return True
    haystack = " ".join(str(descriptor.get(key, "")) for key in
                        ("name", "description", "product")).lower()
    if "video" in str(descriptor.get("media_class", "")).lower():
        return True
    return any(hint in haystack for hint in _WEBCAM_HINTS)


def _has(tokens, group):
    return any(token in group or any(token.startswith(t) for t in group)
               for token in tokens)


def _kind(descriptor):
    """Resolve the fixed icon kind, preferring stable port/media over driver."""
    tokens = _tokens(descriptor)
    gpu = descriptor.get("gpu")
    driver = str(descriptor.get("driver", "")).lower()
    output = not _is_input(descriptor, tokens)

    # A port type is the most reliable signal, so read it first.
    if _has(tokens, _HDMI_TOKENS):
        return "hdmi_output" if output else None
    if _has(tokens, _DIGITAL_TOKENS):
        return "digital" if output else None
    if _has(tokens, _HEADPHONE_TOKENS):
        return "headphones" if output else None
    if _has(tokens, _SPEAKER_TOKENS):
        return "speakers" if output else None
    if _has(tokens, _MIC_TOKENS):
        return "webcam" if _is_webcam(descriptor, tokens) else "microphone"

    # No usable port type: fall back to the media/driver identity.
    if not output:
        return "webcam" if _is_webcam(descriptor, tokens) else "microphone"
    if gpu or "nvidia" in driver or "hdmi" in driver:
        return "hdmi_output"
    if str(descriptor.get("bus", "")).lower() == "usb":
        return None
    if driver:
        return "speakers"
    return None


def _raw_name(descriptor):
    for key in ("name", "description"):
        value = descriptor.get(key)
        if value:
            return str(value).strip()
    return "Unknown audio device"


def _friendly_name(descriptor, kind):
    onboard = bool(descriptor.get("onboard"))
    product = str(descriptor.get("product", "")).strip()
    connector = str(descriptor.get("connector", "")).strip()
    gpu = str(descriptor.get("gpu", "")).strip()
    monitor = str(descriptor.get("monitor", "")).strip()

    if kind == "speakers":
        detail = "onboard audio" if onboard else ""
        return "Speakers (%s)" % detail if detail else "Speakers"
    if kind == "headphones":
        detail = "onboard audio" if onboard else ""
        if connector:
            detail = "%s, %s" % (detail, connector) if detail else connector
        return "Headphones (%s)" % detail if detail else "Headphones"
    if kind == "microphone":
        if str(descriptor.get("bus", "")).lower() == "usb":
            return "%s microphone (USB)" % product if product else \
                "USB microphone"
        return "%s microphone" % product if product else "Microphone"
    if kind == "webcam":
        return "%s webcam microphone" % product if product else \
            "Webcam microphone"
    if kind == "hdmi_output":
        label = monitor or "Monitor"
        if gpu:
            return "%s (HDMI on %s)" % (label, gpu)
        return "%s (HDMI)" % label if monitor else "HDMI output"
    if kind == "digital":
        return "Digital output (optical)"
    return _raw_name(descriptor)


def classify(descriptor):
    """Return ``(friendly_name, icon_kind)`` for one device descriptor.

    ``icon_kind`` is one of :data:`ICON_KINDS`, or ``None`` when the device
    cannot be recognised; then ``friendly_name`` falls back to the raw server
    name so the panel can still show it with a generic icon.
    """
    if not isinstance(descriptor, dict):
        raise TypeError("descriptor must be a mapping")
    kind = _kind(descriptor)
    return _friendly_name(descriptor, kind), kind
