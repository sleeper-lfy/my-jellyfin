"""Small independent UI jobs, owned until their threads have actually stopped."""
from PySide6.QtCore import QThread,Signal,QTimer
from .core import ImportCancelled


class BackgroundJob(QThread):
    done=Signal(object)
    failed=Signal(str)
    progress=Signal(object,object)
    def __init__(self,function,parent):
        super().__init__(parent);self.function=function
    def run(self):
        try:
            result=self.function(self)
            if not self.isInterruptionRequested():self.done.emit(result)
        except ImportCancelled:pass
        except Exception as error:
            if not self.isInterruptionRequested():self.failed.emit(str(error))


def run_background(window,function,done,failed=None):
    job=BackgroundJob(function,window);window._auxiliary_jobs.add(job)
    job.done.connect(done)
    if failed:job.failed.connect(failed)
    def finished():
        window._auxiliary_jobs.discard(job);job.deleteLater()
        if window._closing:QTimer.singleShot(0,window.close)
    job.finished.connect(finished);job.start();return job
