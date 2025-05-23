import usocket as socket
import ubinascii as binascii
import os
import ussl

from .protocol import Websocket, urlparse  


class WebsocketClient(Websocket):
    is_client = True


def connect(uri):
    uri = urlparse(uri)

    sock = socket.socket()
    addr = socket.getaddrinfo(uri.hostname, uri.port)[0][-1]
    sock.connect(addr)

    if uri.protocol == 'wss':
        sock = ussl.wrap_socket(sock, server_hostname=uri.hostname)

    def send_header(header):
        sock.write(header + b'\r\n')

    # Generate 16 random bytes and base64 encode (without newline)
    key = binascii.b2a_base64(os.urandom(16)).strip()

    # Send WebSocket upgrade headers
    send_header(b'GET %s HTTP/1.1' % (uri.path or '/').encode())
    send_header(b'Host: %s:%d' % (uri.hostname.encode(), uri.port))
    send_header(b'Connection: Upgrade')
    send_header(b'Upgrade: websocket')
    send_header(b'Sec-WebSocket-Key: ' + key)
    send_header(b'Sec-WebSocket-Version: 13')
    send_header(b'')

    # Read HTTP response status
    header = sock.readline()[:-2]
    if not header.startswith(b'HTTP/1.1 101 '):
        raise RuntimeError('WebSocket upgrade failed: ' + header.decode())

    # Skip remaining headers
    while True:
        header = sock.readline()[:-2]
        if not header:
            break

    return WebsocketClient(sock)
