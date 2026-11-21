#!/usr/bin/env python3
"""Type text into a headless guest over the QEMU Machine Protocol (issue #424).

Most live ISOs have no SSH server, so the benchmark runner reaches the live
desktop through QEMU's QMP socket instead: it opens the distro's terminal (a
keyboard shortcut recorded per distro in matrix.conf) and types one command
into it. It needs no root, no display and no network, and it drives only the VM
whose QMP socket it is given.

QEMU renamed and reshaped send-key along the way: 10 and older take
{"key": "ret"}, 11 takes {"keys": [{"type": "qcode", "data": "ret"}]}, and the
key names differ between them ("sp" vs "spc", "semi" vs "semicolon"). Every
character therefore keeps a short list of candidate names and QEMU's own
QKeyCode enum is read from query-qmp-schema when the VM offers it, so the names
this QEMU accepts are found once and remembered.

Usage:
  qmp-type.py --qmp PATH type TEXT              # type literal text
  qmp-type.py --qmp PATH combo KEY[-KEY...]     # shortcut, e.g. alt-f2
  qmp-type.py --qmp PATH key KEY [press|release]
  qmp-type.py --qmp PATH screen PATH.ppm        # save the guest screen
Exit codes: 0 ok, 1 no QMP socket or the VM refused every name, 2 bad arguments.
"""
import argparse
import json
import os
import socket
import sys
import time

# Characters the benchmark bootstrap needs. Unshifted characters list the key
# names QEMU has used for them, newest first; shifted ones name the base key
# pressed while shift is held. Anything else is reported as untypeable rather
# than typed as a guess, because a wrong key in a live desktop is worse than a
# missing character.
CHAR_KEYS = {
    ' ': ['spc', 'sp', 'space'],
    '-': ['minus', 'dash'],
    '=': ['equal'],
    '.': ['dot', 'period'],
    ',': ['comma'],
    '/': ['slash'],
    ';': ['semicolon', 'semi'],
    "'": ['apostrophe', 'quote'],
    '`': ['grave_accent', 'grave-accent', 'grave'],
    '[': ['bracket_left', 'lbracket', 'left-bracket', 'bracketleft'],
    ']': ['bracket_right', 'rbracket', 'right-bracket', 'bracketright'],
    '\\': ['backslash'],
    '\n': ['ret'],
    '\t': ['tab'],
}

SHIFTED = {
    ':': ';',
    '|': '\\',
    '!': '1',
    '@': '2',
    '#': '3',
    '$': '4',
    '%': '5',
    '^': '6',
    '&': '7',
    '*': '8',
    '(': '9',
    ')': '0',
    '<': ',',
    '>': '.',
    '?': '/',
    '_': '-',
    '+': '=',
    '"': "'",
    '~': '`',
    '{': '[',
    '}': ']',
}

# Shortcut names as they are written in matrix.conf (xev/gdk style) to the QEMU
# key names they stand for.
KEY_ALIASES = {
    'ctrl': 'ctrl', 'control': 'ctrl',
    'alt': 'alt', 'mod1': 'alt',
    'shift': 'shift', 'super': 'meta_l', 'cmd': 'meta_l', 'win': 'meta_l',
    'f1': 'f1', 'del': 'delete', 'esc': 'esc', 'return': 'ret',
    'space': 'spc', 'enter': 'ret',
}


class Qmp:
    def __init__(self, path):
        self.path = path
        self.sock = None
        self.fifo = None
        self.accepted = {}
        self.payload_form = None
        self.key_names = None

    def connect(self):
        for _ in range(200):
            try:
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.settimeout(10)
                self.sock.connect(self.path)
                self.fifo = self.sock.makefile('rwb')
                self.read()
                self.command('qmp_capabilities')
                self.key_names = self.read_key_names()
                return True
            except (OSError, ValueError, KeyError):
                time.sleep(0.2)
        return False

    def send(self, payload):
        self.fifo.write((json.dumps(payload) + '\n').encode())
        self.fifo.flush()

    def read(self):
        while True:
            line = self.fifo.readline()
            if not line:
                raise OSError('QMP socket closed')
            reply = json.loads(line.decode())
            if 'event' in reply:
                continue
            return reply

    def command(self, name, arguments=None):
        self.send({'execute': name, 'arguments': arguments} if arguments
                  else {'execute': name})
        reply = self.read()
        if 'error' in reply:
            raise RuntimeError('%s: %s' % (reply['error'].get('class', 'error'),
                                           reply['error'].get('desc', '')))
        return reply.get('return')

    def read_key_names(self):
        """The QKeyCode enum this QEMU accepts, when query-qmp-schema offers it."""
        try:
            schema = self.command('query-qmp-schema')
        except RuntimeError:
            return None
        for entry in schema:
            values = entry.get('values') or []
            if 'ret' in values and 'shift' in values and (
                    'spc' in values or 'sp' in values):
                return set(values)
        return None

    def resolve(self, candidates):
        """The key name this QEMU answers for one character's candidate names."""
        if self.key_names:
            for name in candidates:
                if name in self.key_names:
                    return name
            return None
        cached = self.accepted.get(tuple(candidates))
        if cached:
            return cached
        for name in candidates:
            if self.sendkey([name]):
                self.accepted[tuple(candidates)] = name
                return name
        return None

    def sendkey(self, names, hold=None):
        # QEMU 11 takes a list of chord keys, each a discriminated union, and
        # presses them together, releasing them in reverse; 10 and older take
        # one "key" plus an optional "hold". Whichever the VM answers is kept.
        forms = [self.payload_form] if self.payload_form else ('qemu11', 'old')
        for form in forms:
            if form == 'qemu11':
                arguments = {'keys': [{'type': 'qcode', 'data': name}
                                      for name in names]}
            else:
                if len(names) > 1:
                    continue
                arguments = {'key': names[0]}
                if hold is not None:
                    arguments['hold'] = hold
            try:
                self.command('send-key', arguments)
            except RuntimeError:
                continue
            self.payload_form = form
            return True
        return False

    def chord(self, candidate_lists):
        """Press the keys of one shortcut or character together."""
        names = []
        for candidates in candidate_lists:
            name = self.resolve(candidates)
            if name is None:
                return False
            names.append(name)
        if self.sendkey(names):
            return True
        # QEMU 10 has no chord: hold the modifiers, tap the last key, release.
        for name in names[:-1]:
            if not self.sendkey([name], hold=True):
                return False
        ok = self.sendkey([names[-1]])
        for name in reversed(names[:-1]):
            self.sendkey([name], hold=False)
        return ok

    def character(self, char):
        if char.isupper():
            return self.chord([['shift'], [char.lower()]])
        if char.isalnum():
            return self.chord([[char]])
        if char in CHAR_KEYS:
            return self.chord([CHAR_KEYS[char]])
        if char in SHIFTED:
            base = SHIFTED[char]
            return self.chord([['shift'], CHAR_KEYS.get(base, [base])])
        return False

    def type_text(self, text, between):
        failed = []
        for char in text:
            if not self.character(char):
                failed.append(char)
            time.sleep(between)
        return failed

    def shortcut(self, keys):
        """One shortcut, for example ctrl-alt-t or alt-f2, pressed together."""
        return self.chord([[key, KEY_ALIASES.get(key, key)] for key in keys])

    def screen(self, path):
        self.command('screendump', {'filename': os.path.abspath(path)})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--qmp', required=True)
    parser.add_argument('--delay', type=float, default=0.03,
                        help='seconds between keys (default 0.03)')
    sub = parser.add_subparsers(dest='action', required=True)
    typep = sub.add_parser('type')
    typep.add_argument('text')
    combop = sub.add_parser('combo')
    combop.add_argument('keys', help='shortcut, for example alt-f2 or ctrl-alt-t')
    keyp = sub.add_parser('key')
    keyp.add_argument('name')
    keyp.add_argument('hold', nargs='?', default='')
    screenp = sub.add_parser('screen')
    screenp.add_argument('path')
    args = parser.parse_args(argv)

    if args.action == 'combo':
        keys = [key for key in args.keys.split('-') if key]
        if not keys:
            print('empty shortcut', file=sys.stderr)
            return 2
    if not os.path.exists(args.qmp):
        print('no QMP socket at %s' % args.qmp, file=sys.stderr)
        return 1
    qmp = Qmp(args.qmp)
    if not qmp.connect():
        print('could not talk QMP to %s' % args.qmp, file=sys.stderr)
        return 1

    if args.action == 'type':
        failed = qmp.type_text(args.text, args.delay)
        if failed:
            print('UNTYPEABLE: %s' % ' '.join(repr(c) for c in failed),
                  file=sys.stderr)
            return 2
        return 0
    if args.action == 'combo':
        return 0 if qmp.shortcut(keys) else 1
    if args.action == 'key':
        hold = None
        if args.hold in ('press', 'release'):
            hold = args.hold == 'press'
        return 0 if qmp.sendkey([args.name], hold) else 1
    qmp.screen(args.path)
    print(args.path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
