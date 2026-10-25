"""Bounded application logs and automatic Qt event-loop stall reports."""
from datetime import datetime, timezone
import faulthandler
import logging
from logging.handlers import RotatingFileHandler
import platform
import sys
import threading
import time
import traceback

from PySide6.QtCore import QObject, QTimer


def configure_logging(directory):
    handler=RotatingFileHandler(directory/'diagnostics.log',maxBytes=5*1024*1024,backupCount=3,encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    root=logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    logging.info('Starting Lumen: Python %s; %s; data directory=%s',platform.python_version(),platform.platform(),directory)
    previous=sys.excepthook
    def unhandled(kind,value,trace):
        logging.critical('Unhandled application exception',exc_info=(kind,value,trace))
        previous(kind,value,trace)
    sys.excepthook=unhandled
    return handler


class UiWatchdog(QObject):
    """Capture all Python stacks while a GUI heartbeat is late by 3 seconds.

    Monitoring and file I/O run on a daemon thread, independently of Qt's event
    loop. A separate CPython C watchdog records a fallback after 5 seconds,
    including a native wait that prevents Python threads from taking the GIL.
    """
    def __init__(self, directory, parent=None, *, threshold=3, clock=time.monotonic, start=True):
        super().__init__(parent)
        self.directory=directory
        self.threshold=threshold
        self.clock=clock
        self.last_beat=clock()
        self.stalled=False
        self.last_dump=0
        self.gui_thread=threading.get_ident()
        self.stop_event=threading.Event()
        self.timer=QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.beat)
        if start:
            self.timer.start()
            self.thread=threading.Thread(target=self._run,name='UiWatchdog',daemon=True)
            self.thread.start()

    def beat(self):
        self.last_beat=self.clock()

    def check(self):
        current=self.clock()
        delay=current-self.last_beat
        if delay<self.threshold:
            if self.stalled:
                logging.warning('Qt event loop recovered after a recorded stall')
                self.stalled=False
            return
        if self.stalled and current-self.last_dump<10:return
        self.stalled=True
        self.last_dump=current
        self._dump(delay)

    def _dump(self, delay):
        path=self.directory/'ui-hangs.log'
        try:
            if path.exists() and path.stat().st_size>=4*1024*1024:
                old=path.with_name('ui-hangs.log.2')
                old.unlink(missing_ok=True)
                previous=path.with_name('ui-hangs.log.1')
                if previous.exists():previous.replace(old)
                path.replace(previous)
            with path.open('a',encoding='utf-8') as stream:
                stream.write(f'\n{datetime.now(timezone.utc).isoformat()} Qt heartbeat delayed {delay:.2f}s; GUI thread={self.gui_thread}\n')
                frame=sys._current_frames().get(self.gui_thread)
                if frame:
                    stream.write('GUI Python stack:\n')
                    stream.writelines(traceback.format_stack(frame))
                stream.flush()
                faulthandler.dump_traceback(file=stream,all_threads=True)
            logging.warning('Qt event loop delayed %.2fs; stacks saved to %s',delay,path)
        except (OSError,RuntimeError):
            logging.exception('Could not save Qt stall report')

    def _run(self):
        # Python monitoring cannot run if native Qt code is holding the GIL.
        # CPython's C watchdog can still dump stacks in that case. Rearm it
        # from this thread only when Qt has delivered a newer heartbeat.
        stream=None;armed_beat=None;last_arm=0
        path=self.directory/'ui-native-hangs.log'
        try:
            while not self.stop_event.is_set():
                current=self.clock()
                if self.last_beat!=armed_beat and current-last_arm>=1:
                    try:
                        faulthandler.cancel_dump_traceback_later()
                        if stream is not None and stream.tell()>=4*1024*1024:
                            stream.close();stream=None
                            old=path.with_name(path.name+'.2');old.unlink(missing_ok=True)
                            previous=path.with_name(path.name+'.1')
                            if previous.exists():previous.replace(old)
                            if path.exists():path.replace(previous)
                        if stream is None:
                            stream=path.open('a',encoding='utf-8')
                            stream.write('\n'+datetime.now(timezone.utc).isoformat()+' Native Qt watchdog (one dump per stalled heartbeat)\n');stream.flush()
                        # One-shot: a permanently stuck process cannot grow
                        # this file indefinitely while Python is unavailable.
                        faulthandler.dump_traceback_later(max(5,self.threshold+2),file=stream,repeat=False)
                        armed_beat=self.last_beat;last_arm=current
                    except (OSError,RuntimeError):
                        logging.exception('Could not arm native Qt stall report')
                self.check()
                if self.stop_event.wait(.5):break
        finally:
            faulthandler.cancel_dump_traceback_later()
            if stream is not None:stream.close()

    def stop(self):
        self.timer.stop()
        self.stop_event.set()
