"""Small, token-free LAN discovery. HTTP authorization remains mandatory."""
import ipaddress
import json
import re
import socket
import threading
import time

DISCOVERY_PORT = 8098
PREFIX = b'LUMEN_DISCOVER_V1 '


class DiscoveryResponder:
    def __init__(self, host, http_port, port=DISCOVERY_PORT):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.socket.bind((host, port))
            self.socket.settimeout(.25)
        except OSError:
            self.socket.close()
            raise
        self.port = self.socket.getsockname()[1]
        self.http_port = http_port
        self.closed = threading.Event()
        self.thread = threading.Thread(target=self.run, name='LumenDiscovery', daemon=True)
        self.thread.start()

    def run(self):
        recent = {}
        while not self.closed.is_set():
            try:
                request, peer = self.socket.recvfrom(256)
                if not ipaddress.ip_address(peer[0]).is_private or not re.fullmatch(PREFIX + b'[0-9a-f]{32}', request):
                    continue
                stamp = time.monotonic()
                if stamp - recent.get(peer[0], -1) < .25:
                    continue
                if len(recent) >= 256:
                    recent.clear()
                recent[peer[0]] = stamp
                response = {'service': 'lumen', 'api_version': 1, 'port': self.http_port,
                            'nonce': request[len(PREFIX):].decode('ascii'), 'name': socket.gethostname()[:64]}
                self.socket.sendto(json.dumps(response).encode('utf-8'), peer)
            except socket.timeout:
                continue
            except OSError:
                break

    def stop(self):
        self.closed.set()
        self.thread.join(timeout=1)
        self.socket.close()
