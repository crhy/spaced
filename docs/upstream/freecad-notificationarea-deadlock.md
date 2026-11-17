# FreeCAD 1.1.4 flatpak GUI freeze — upstream bug report text

Status: drafted on 2026-11-16 while investigating the freeze (task f078, issue
#425). **Not filed upstream yet** — filing it against FreeCAD is rhY's call, and
this copy exists so the text is not lost. The deadlock is FreeCAD's; the Qt 6.11
half is listed separately below.

What Spaced ships while this stays upstream: the system flatpak override
`/var/lib/flatpak/overrides/org.freecad.FreeCAD` (`[Environment]` +
`QT_LOGGING_RULES=qt.accessibility.atspi=false`), staged by the image and carried
to installed systems by the `spaced-meta` postinst migration
`freecad-flatpak-override-11.26.3`. See the [resolution record](../FIXES.md).

---

Filed against FreeCAD (the deadlock is FreeCAD's). Qt 6.11 is a secondary
contributor; that half is listed separately below.

---

## Title

GUI deadlocks at startup: `NotificationArea` re-locks its own `std::mutex` when a
Qt warning is routed through `Base::Console()` (Qt 6.11 AT-SPI adaptor)

## Environment

- FreeCAD 1.1.4, Flathub flatpak `org.freecad.FreeCAD`, commit
  `4fd3bf320d9566a27e60069fc8387448aaa3a094`, runtime `org.kde.Platform/6.11`,
  Qt 6.11.3 (built `RelWithDebInfo`, `-DFC_FLATPAK=ON`).
- X11 desktop (Compiz/MATE), no document loaded, `--safe-mode` also freezes.
- The official FreeCAD 1.1.4 AppImage on the same machine and session does not
  freeze.

## Steps

1. `flatpak run org.freecad.FreeCAD`
2. The Start page draws, then stops repainting after ~20-30 s. The window manager
   reports the window as not responding (it no longer answers `_NET_WM_PING`), CPU
   is 0 %, and a window close request is never answered.
3. Reproduced on 3/3 fresh launches; the main thread sits in
   `futex_do_wait` for minutes on end.

## Actual result

Main thread is blocked in `pthread_mutex_lock` on a mutex it already owns:

```
#0  __lll_lock_wait ()
#1  pthread_mutex_lock ()
#2  __gthread_mutex_lock (__mutex=0x559b84ce9358)
#3  std::mutex::lock ()
#4  std::lock_guard<std::mutex>::lock_guard (__m=...)
#5  Gui::NotificationArea::pushNotification (this=0x559b84c85b60, ..., level=Base::LogStyle::Warning)
      src/Gui/NotificationArea.cpp:1052
#6  NotificationAreaObserver::sendLog (..., content=Base::ContentType::Untranslated)
      src/Gui/NotificationArea.cpp:313
#7  Base::ConsoleSingleton::notifyPrivate (...)   src/Base/Console.cpp:325
#8  Base::ConsoleSingleton::notify<Warning, All, Untranslated> (...)
#9  Base::ConsoleSingleton::send<...> (...)
#10 Base::ConsoleSingleton::warning<char const*> (...)
#12 messageHandler (type=..., msg=...)           src/Gui/Application.cpp:2221
#13 qt_message_output (...)
#14 QDebug::~QDebug ()
#15 AtSpiAdaptor::notify(QAccessibleEvent*) [clone .cold]   libQt6Gui.so.6.11.3
#16 QWidgetTextControlPrivate::_q_contentsChanged(int, int, int)
#17 doActivate<false> (...)
#18 QTextDocument::contentsChange(int, int, int)
#19 QTextDocumentPrivate::clear()
#20 QTextDocument::setHtml(QString const&)
#21 QLabelPrivate::ensureTextPopulated() const
#22 QLabelPrivate::ensureTextLayouted() const
#23 QLabelPrivate::sizeForWidth(int) const
#24 QLabel::minimumSizeHint() const
#25 QLabel::sizeHint() const
#26 Gui::NotificationLabel::updateSize (this=0x559b89053df0, ...)
      src/Gui/NotificationBox.cpp:186
#27 Gui::NotificationLabel::reuseNotification (...)  src/Gui/NotificationBox.cpp:170
#28 Gui::NotificationLabel::NotificationLabel (...)  src/Gui/NotificationBox.cpp:145
#29 Gui::NotificationBox::showText (...)             src/Gui/NotificationBox.cpp:401
#30 Gui::NotificationArea::showInNotificationArea (this=0x559b84c85b60)
      src/Gui/NotificationArea.cpp:1294
#31 doActivate<false> (...)
#32 QTimer::timeout(QTimer::QPrivateSignal)
...
#38 QCoreApplication::exec()
#39 Gui::Application::runApplication()
```

Frames 5 and 30 have the same `this` (`0x559b84c85b60`), so both lock the same
member `NotificationAreaP::mutexNotification` (`std::mutex`, src/Gui/NotificationArea.cpp:124)
on the same thread. Every other thread is parked elsewhere (15 OpenBLAS workers
in `pthread_cond_wait`, the `QDBusConnection` poller, `QXcbEventQueue` in
`poll`, one pango font thread), so the holder is the main thread itself.

## Cause

1. `NotificationArea::showInNotificationArea()` (src/Gui/NotificationArea.cpp:1140)
   takes `lock_guard<std::mutex> g(pImp->mutexNotification);` at line 1143 and
   then, still holding it, renders the notification: `NotificationBox::showText()`
   at line 1294 → `NotificationLabel` → `updateSize()` → `QLabel::sizeHint()`
   (src/Gui/NotificationBox.cpp:186).
2. Laying out that label's HTML text makes Qt's AT-SPI accessibility adaptor
   emit a warning (`AtSpiAdaptor::notify`, the `.cold` error branch, message
   `qt.accessibility.atspi: Received text event for invalid interface.`).
3. FreeCAD installs a Qt message handler (src/Gui/Application.cpp, `messageHandler`)
   that maps `QtWarningMsg` to `Base::Console().warning("%s\n", output.constData())`
   (line 2221).
4. `Base::Console()` dispatches to the GUI's `NotificationAreaObserver::sendLog`
   (line 313) → `NotificationArea::pushNotification()` → `lock_guard` on the
   same non-recursive `std::mutex` (line 1052) → self-deadlock.

The console of a frozen run shows the warning 52 times before the freeze
(`(qt.accessibility.atspi) Received text event for invalid interface.`), which
matches the 52 label text updates that happened before the fatal one.

## Expected result

The GUI stays responsive; a Qt warning from inside widget layout must not
re-enter the notification subsystem that is currently locked.

## Suggested fixes (any one is enough)

- Do not call `Base::Console()` while `mutexNotification` is held: collect what
  has to be reported under the lock and dispatch it after the lock is released.
- Or make the re-entrancy explicit: a `thread_local` guard in
  `NotificationAreaObserver::sendLog` that queues the message instead of
  dispatching it while the same thread is inside `showInNotificationArea()`.
- Or replace `std::mutex mutexNotification` with `std::recursive_mutex`
  (least invasive, keeps the current structure).
- Or stop holding the mutex across UI rendering (`NotificationBox::showText()`
  and `QLabel::sizeHint()` are Qt calls and can run arbitrary callbacks).

## Secondary: Qt 6.11 side

- `AtSpiAdaptor::notify()` warns for ordinary `QLabel` HTML text updates
  ("Received text event for invalid interface.") from inside widget layout.
  Any application that installs a `qSetMessageHandler` gets re-entered there.
- Qt 6.11 has no switch to turn the AT-SPI bridge off: `QT_ACCESSIBILITY` and
  `QT_NO_ATSPI` are not consulted by `libQt6Gui.so.6.11.3` (only
  `QT_LINUX_ACCESSIBILITY_ALWAYS_ON` is present), and the bridge is always
  reachable inside a flatpak sandbox because flatpak injects
  `AT_SPI_BUS_ADDRESS=unix:path=/run/flatpak/at-spi-bus`. `QT_LOGGING_RULES`
  filtering happens before the installed handler is called, which is what makes
  the workaround below effective.

## Workaround (measured)

```
flatpak run --env=QT_LOGGING_RULES=qt.accessibility.atspi=false org.freecad.FreeCAD
```

## Attachments

`bt-all.txt` (all 19 threads, symbolized with `org.freecad.FreeCAD.Debug` +
`org.kde.Sdk//6.11`), the frozen run console log, and the A/B responsiveness
transcripts.

## Upstream status (checked 2026-11-16)

Already fixed upstream: FreeCAD PR #33819 "Gui: Fix NotificationArea deadlock when showing a notification"
(commit 920d14763, releases the lock before `NotificationBox::showText()`), backported to `releases/FreeCAD-26-3`
by PR #33964. It is **not** in `releases/FreeCAD-1-1`, so the 1.1.4 flatpak still freezes. Keep the Spaced override
(`QT_LOGGING_RULES=qt.accessibility.atspi=false`) until Flathub ships a FreeCAD release containing that commit,
then remove it.
