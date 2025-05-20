import ure as re
import ustruct as struct
import os
import usocket as socket

def const(x): return x  # MicroPython doesn't auto-support const()

# Opcodes
OP_CONT = const(0x0)
OP_TEXT = const(0x1)
OP_BYTES = const(0x2)
OP_CLOSE = const(0x8)
OP_PING = const(0x9)
OP_PONG = const(0xA)

# Close codes
CLOSE_OK = const(1000)
CLOSE_TOO_BIG = const(1009)

# Basic URI parser
class URI:
    def __init__(self, protocol, hostname, port, path):
        self.protocol = protocol
        self.hostname = hostname
        self.port = port
        self.path = path

def urlparse(uri):
    """Parse ws:// URLs"""
    match = re.match(r'(wss|ws)://([A-Za-z0-9\.-]+)(?::([0-9]+))?(/.*)?', uri)
    if match:
        protocol, host, port, path = match.group(1), match.group(2), match.group(3), match.group(4)
        if not port:
            port = 443 if protocol == 'wss' else 80
        if not path:
            path = '/'
        return URI(protocol, host, int(port), path)
    raise ValueError("Invalid WebSocket URI")

class NoDataException(Exception): pass
class ConnectionClosed(Exception): pass

class Websocket:
    is_client = False

    def __init__(self, sock):
        self.sock = sock
        self.open = True

    def read_frame(self):
        hdr = self.sock.read(2)
        if not hdr:
            raise NoDataException
        byte1, byte2 = struct.unpack('!BB', hdr)
        fin = byte1 & 0x80
        opcode = byte1 & 0x0F
        masked = byte2 & 0x80
        length = byte2 & 0x7F

        if length == 126:
            length = struct.unpack('!H', self.sock.read(2))[0]
        elif length == 127:
            length = struct.unpack('!Q', self.sock.read(8))[0]

        if masked:
            mask = self.sock.read(4)
        data = self.sock.read(length)
        if masked:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        return fin, opcode, data

    def write_frame(self, opcode, data=b''):
        fin = 0x80
        mask_bit = 0x80 if self.is_client else 0
        length = len(data)

        hdr = bytearray()
        hdr.append(fin | opcode)
        if length < 126:
            hdr.append(mask_bit | length)
        elif length < (1 << 16):
            hdr.append(mask_bit | 126)
            hdr += struct.pack('!H', length)
        else:
            hdr.append(mask_bit | 127)
            hdr += struct.pack('!Q', length)

        if self.is_client:
            mask = os.urandom(4)
            hdr += mask
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))

        self.sock.write(hdr + data)

    def recv(self):
        while self.open:
            fin, opcode, data = self.read_frame()
            if opcode == OP_TEXT:
                return data.decode()
            elif opcode == OP_BYTES:
                return data
            elif opcode == OP_CLOSE:
                self.open = False
                return None
            elif opcode == OP_PING:
                self.write_frame(OP_PONG, data)
            elif opcode == OP_PONG:
                continue

    def send(self, msg):
        if isinstance(msg, str):
            self.write_frame(OP_TEXT, msg.encode())
        elif isinstance(msg, bytes):
            self.write_frame(OP_BYTES, msg)

    def close(self, code=CLOSE_OK, reason=''):
        payload = struct.pack('!H', code) + reason.encode()
        self.write_frame(OP_CLOSE, payload)
        self.open = False
        self.sock.close()
