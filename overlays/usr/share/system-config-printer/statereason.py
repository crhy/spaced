#!/usr/bin/python3

## Copyright (C) 2007, 2008, 2009, 2010, 2012, 2013, 2014 Red Hat, Inc.
## Authors:
##  Tim Waugh <twaugh@redhat.com>
##  Jiri Popelka <jpopelka@redhat.com>

## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.

## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.

## You should have received a copy of the GNU General Public License
## along with this program; if not, write to the Free Software
## Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

## Spaced Linux (issue #440): this file owns
## /usr/share/system-config-printer/statereason.py, a path Debian's
## system-config-printer-common also owns, so spaced-mate-default-settings'
## preinst runs "dpkg-divert --package spaced-mate-default-settings --rename
## --add" and moves the Debian copy to statereason.py.distrib (postrm removes
## the diversion).  This keeps a thin override of that module rather than a
## full copy: it loads the diverted file and replaces only get_level (),
## which defaults every reason that is not '*-report', '*-warning' or on its
## special list to ERROR - so a queue reporting 'cups-waiting-for-job-completed'
## or 'media-low' during a successful print showed "Printer error" - and adds
## the "Printing…" wording for the reasons a printing queue reports.  Every
## other future Debian change to statereason.py keeps applying.

import importlib.machinery
import importlib.util
import os


def _load_diverted_module():
    """Load Debian's statereason.py, wherever dpkg's diversion left it."""
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.join(here, 'statereason.py.distrib'),
                 '/usr/share/system-config-printer/statereason.py.distrib',
                 '/usr/share/system-config-printer/statereason.py'):
        if not os.path.exists(path):
            continue
        if os.path.realpath(path) == os.path.realpath(__file__):
            continue  # this override itself, not the file it overrides
        # The diverted file is named statereason.py.distrib, so a loader
        # must be given explicitly instead of guessing from the suffix.
        loader = importlib.machinery.SourceFileLoader('statereason_distrib',
                                                      path)
        spec = importlib.util.spec_from_loader('statereason_distrib', loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return module
    raise RuntimeError(
        'statereason.py: cannot find the Debian statereason.py to override; '
        'the spaced-mate-default-settings dpkg diversion is missing')


_distrib = _load_diverted_module()

StateReason = _distrib.StateReason


def _spaced_get_level(self):
    # Spaced Linux (issue #440): the IPP printer-state-reasons registry
    # says what a level is - the '*-error' suffix marks real errors,
    # '*-warning' marks warnings, and everything else ('*-report', or
    # historically unsuffixed reasons like 'media-low' and the normal
    # printing reason 'cups-waiting-for-job-completed') is a report.
    # 'stopped' is the one unsuffixed reason that is an error.
    if self.level is not None:
        return self.level

    if self.reason.endswith ("-error") or self.reason == "stopped":
        self.level = self.ERROR
    elif self.reason.endswith ("-warning"):
        self.level = self.WARNING
    else:
        self.level = self.REPORT

    return self.level


# Spaced Linux (issue #440): these are what a queue reports while a job
# prints normally, so say so instead of leaving them to the generic report
# wording in Debian's get_description ().
_printing_messages = {
    'cups-waiting-for-job-completed': (_("Printing…"),
                                       _("Printer '%s' is printing.")),
    'processing': (_("Printing…"),
                   _("Printer '%s' is printing.")),
}
_debian_get_description = StateReason.get_description


def _spaced_get_description(self):
    reason = self.get_reason ()
    if reason in _printing_messages:
        title, text = _printing_messages[reason]
        try:
            text = text % self.get_printer ()
        except TypeError:
            # Probably an incorrect translation, missing a '%s'.
            pass
        return (title, text)
    return _debian_get_description(self)


StateReason.get_level = _spaced_get_level
StateReason.get_description = _spaced_get_description
