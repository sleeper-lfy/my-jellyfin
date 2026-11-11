"""Logging setup usable without importing the GUI runtime."""
import logging
from logging.handlers import RotatingFileHandler
import platform
import sys

def configure_logging(directory, filename='diagnostics.log'):
    handler=RotatingFileHandler(directory/filename,maxBytes=5*1024*1024,backupCount=3,encoding='utf-8')
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
