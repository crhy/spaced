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

## Spaced Linux ships this copy over the Debian one (issue #440).  Upstream's
## get_level () defaults every reason that is not '*-report', '*-warning' or on
## its special list to ERROR, but a queue that is printing successfully reports
## reasons like 'cups-waiting-for-job-completed' or 'media-low' all the time -
## so the tray applet, print monitor and printer manager showed "Printer error"
## during a normal print job until it completed.  Spaced classifies by the IPP
## suffix rules instead: only '*-error' reasons (or 'stopped') are errors,
## '*-warning' reasons are warnings, and '*-report' or unsuffixed reasons are
## reports, not errors.  Reasons that mean "a job is printing" now describe
## themselves as "Printing…" instead of an error.

import cups
import os
import config
import gettext
gettext.install(domain=config.PACKAGE, localedir=config.localedir)

class StateReason:
    REPORT=1
    WARNING=2
    ERROR=3

    LEVEL_ICON={
        REPORT: "dialog-information",
        WARNING: "dialog-warning",
        ERROR: "dialog-error"
        }

    def __init__(self, printer, reason, ppdcache=None):
        self.printer = printer
        self.reason = reason
        self.level = None
        self.canonical_reason = None
        self._ppd = None
        if ppdcache:
            ppdcache.fetch_ppd (printer, self._got_ppd)

    def _got_ppd (self, name, result, exc):
        self._ppd = result

    def get_printer (self):
        return self.printer

    def get_level (self):
        if self.level is not None:
            return self.level

        # Spaced Linux (issue #440): the IPP printer-state-reasons registry
        # says what a level is - the '*-error' suffix marks real errors,
        # '*-warning' marks warnings, and everything else ('*-report', or
        # historically unsuffixed reasons like 'media-low' and the normal
        # printing reason 'cups-waiting-for-job-completed') is a report.
        # 'stopped' is the one unsuffixed reason that is an error.
        if self.reason.endswith ("-error") or self.reason == "stopped":
            self.level = self.ERROR
        elif self.reason.endswith ("-warning"):
            self.level = self.WARNING
        else:
            self.level = self.REPORT

        return self.level

    def get_reason (self):
        if self.canonical_reason:
            return self.canonical_reason

        level = self.get_level ()
        reason = self.reason
        if level == self.WARNING and reason.endswith ("-warning"):
            reason = reason[:-8]
        elif level == self.ERROR and reason.endswith ("-error"):
            reason = reason[:-6]
        self.canonical_reason = reason
        return self.canonical_reason

    def __repr__ (self):
        self.get_level()
        if self.level == self.REPORT:
            level = "REPORT"
        elif self.level == self.WARNING:
            level = "WARNING"
        else:
            level = "ERROR"

        return "<statereason.StateReason (%s,%s,%s)>" % (level,
                                                         self.get_printer (),
                                                         self.get_reason ())

    def get_description (self):
        messages = {
            'toner-low': (_("Toner low"),
                          _("Printer '%s' is low on toner.")),
            'toner-empty': (_("Toner empty"),
                            _("Printer '%s' has no toner left.")),
            'cover-open': (_("Cover open"),
                           _("The cover is open on printer '%s'.")),
            'door-open': (_("Door open"),
                          _("The door is open on printer '%s'.")),
            'media-low': (_("Paper low"),
                          _("Printer '%s' is low on paper.")),
            'media-empty': (_("Out of paper"),
                            _("Printer '%s' is out of paper.")),
            'marker-supply-low': (_("Ink low"),
                                  _("Printer '%s' is low on ink.")),
            'marker-supply-empty': (_("Ink empty"),
                                    _("Printer '%s' has no ink left.")),
            'offline': (_("Printer off-line"),
                        _("Printer '%s' is currently off-line.")),
            'connecting-to-device': (_("Not connected?"),
                                     _("Printer '%s' may not be connected.")),
            'other': (_("Printer error"),
                      _("There is a problem on printer '%s'.")),

            'cups-missing-filter': (_("Printer configuration error"),
                                    _("There is a missing print filter for "
                                      "printer '%s'.")),

            # Spaced Linux (issue #440): these are what a queue reports while
            # a job prints normally, so say so instead of leaving them to the
            # generic report wording.
            'cups-waiting-for-job-completed': (_("Printing…"),
                                               _("Printer '%s' is printing.")),
            'processing': (_("Printing…"),
                           _("Printer '%s' is printing.")),
            }
        try:
            (title, text) = messages[self.get_reason ()]
            try:
                text = text % self.get_printer ()
            except TypeError:
                # Probably an incorrect translation, missing a '%s'.
                pass
        except KeyError:
            if self.get_level () == self.REPORT:
                title = _("Printer report")
            elif self.get_level () == self.WARNING:
                title = _("Printer warning")
            elif self.get_level () == self.ERROR:
                title = _("Printer error")

            reason = self.get_reason ()
            if self._ppd:
                try:
                    schemes = ["text", "http", "help", "file"]
                    localized_reason = ""
                    for scheme in schemes:
                        lreason = self._ppd.localizeIPPReason(self.reason,
                                                              scheme)
                        if lreason is not None:
                            localized_reason = localized_reason + lreason + ", "
                    if localized_reason != "":
                        reason = localized_reason[:-2]
                except RuntimeError:
                    pass

            text = (_("Printer '%s': '%s'.") % (self.get_printer (), reason))
        return (title, text)

    def get_tuple (self):
        return (self.get_level (), self.get_printer (), self.get_reason ())

    def __eq__(self, other):
      if type (other) != type (self):
            return False
      return self.get_level () == other.get_level ()

    def __lt__(self, other):
      if type (other) != type (self):
            return False
      return self.get_level () < other.get_level ()
