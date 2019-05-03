from collections import defaultdict
from os import path
from os import strerror
from os import unlink
from socket import AF_INET
from socket import AF_INET6
from socket import AF_UNIX
from socket import IPPROTO_TCP
from socket import IPPROTO_UDP
from socket import SHUT_WR
from socket import SO_ERROR
from socket import SOCK_DGRAM
from socket import SOCK_STREAM
from socket import socket
from socket import SOL_SOCKET
from ssl import MemoryBIO
from ssl import SSLWantReadError
from ssl import SSLWantWriteError
from struct import calcsize
from struct import unpack
from types import coroutine
from .._syscalls import SYSCALL_SOCKET_ACCEPT
from .._syscalls import SYSCALL_SOCKET_CLOSE
from .._syscalls import SYSCALL_SOCKET_CONNECT
from .._syscalls import SYSCALL_SOCKET_LISTEN
from .._syscalls import SYSCALL_SOCKET_RECV
from .._syscalls import SYSCALL_SOCKET_RECV_INTO
from .._syscalls import SYSCALL_SOCKET_RECVFROM
from .._syscalls import SYSCALL_SOCKET_RECVFROM_INTO
from .._syscalls import SYSCALL_SOCKET_SEND
from .._syscalls import SYSCALL_SOCKET_SENDTO
from .._syscalls import SYSCALL_SOCKET_SHUTDOWN


def _get_socket_exception_from_fileno(fileno):
    sock = socket(fileno=fileno)
    code = sock.getsockopt(SOL_SOCKET, SO_ERROR)
    text = strerror(code)
    sock.detach()

    return OSError(code, text)


class SocketBase:
    __slots__ = ('_socket', )

    def __get_socket_opt_reuse_addr(self):
        if self._opt_reuse_addr:
            return bool(self._socket.getsockopt(SOL_SOCKET, self._opt_reuse_addr))

        return False

    def __set_socket_opt_reuse_addr(self, value):
        if self._opt_reuse_addr:
            self._socket.setsockopt(SOL_SOCKET, self._opt_reuse_addr, 1 if value else 0)

    def __get_socket_opt_reuse_port(self):
        if self._opt_reuse_port:
            return bool(self._socket.getsockopt(SOL_SOCKET, self._opt_reuse_port))

        return False

    def __set_socket_opt_reuse_port(self, value):
        if self._opt_reuse_port:
            self._socket.setsockopt(SOL_SOCKET, self._opt_reuse_port, 1 if value else 0)

    def __get_socket_opt_peer_cred(self):
        if self._opt_peer_cred:
            # FIXME: pid, uid, gid order may not be respected by non-Linux *nixes.
            credentials = self._socket.getsockopt(SOL_SOCKET, self._opt_peer_cred, calcsize("3i"))

            return unpack("3i", credentials)

        return -1, -1, -1

    reuse_addr = property(__get_socket_opt_reuse_addr, __set_socket_opt_reuse_addr)
    reuse_port = property(__get_socket_opt_reuse_port, __set_socket_opt_reuse_port)
    peer_cred = property(__get_socket_opt_peer_cred)

    def __init__(self, socket_family=None, socket_type=None, socket_protocol=None, fileno=None, socket_obj=None):
        if socket_obj:
            self._socket = socket_obj
        elif fileno:
            self._socket = socket(fileno=fileno)
        else:
            self._socket = socket(socket_family, socket_type, socket_protocol)
            self._socket.setblocking(False)

    def getpeername(self):
        return self._socket.getpeername()

    def getsockname(self):
        return self._socket.getsockname()

    @coroutine
    def close(self):
        return (yield SYSCALL_SOCKET_CLOSE, self._socket)

    @coroutine
    def shutdown(self):
        return (yield SYSCALL_SOCKET_SHUTDOWN, self._socket, SHUT_WR)


try:
    from socket import SO_REUSEADDR # pylint: disable=C0412

    SocketBase._opt_reuse_addr = SO_REUSEADDR
except ImportError:
    SocketBase._opt_reuse_addr = None

try:
    from socket import SO_REUSEPORT # pylint: disable=C0412

    SocketBase._opt_reuse_port = SO_REUSEPORT
except ImportError:
    SocketBase._opt_reuse_port = None

try:
    # FIXME: Some OSes support SO_PEERCRED while Python's socket module does not export this constant. \
    # FIXME: They say SO_PEERCRED equals 17 on most x86/x64 Linuxes
    from socket import SO_PEERCRED # pylint: disable=C0412

    SocketBase._opt_peer_cred = SO_PEERCRED
except ImportError:
    SocketBase._opt_peer_cred = None


_IP_FAMILY = {
    4: AF_INET,
    6: AF_INET6
}


class UdpSocket(SocketBase):
    def __init__(self, version=4):
        super().__init__(socket_family=_IP_FAMILY[version], socket_type=SOCK_DGRAM, socket_protocol=IPPROTO_UDP)

    def bind(self, addr):
        self._socket.bind(addr)

    @coroutine
    def recvfrom(self, size):
        return (yield SYSCALL_SOCKET_RECVFROM, self._socket, size)

    @coroutine
    def recvfrom_into(self, data, size):
        return (yield SYSCALL_SOCKET_RECVFROM_INTO, self._socket, data, size)

    @coroutine
    def sendto(self, data, addr):
        return (yield SYSCALL_SOCKET_SENDTO, self._socket, data, addr)


class TcpClientSocket(SocketBase):
    CAN_BE_CLIENT = True
    CAN_BE_SERVER = False

    def __init__(self, version=4):
        super().__init__(socket_family=_IP_FAMILY[version], socket_type=SOCK_STREAM, socket_protocol=IPPROTO_TCP)

    def bind(self, addr):
        self._socket.bind(addr)

    @coroutine
    def connect(self, addr):
        return (yield SYSCALL_SOCKET_CONNECT, self._socket, addr)

    @coroutine
    def recv(self, size):
        return (yield SYSCALL_SOCKET_RECV, self._socket, size)

    @coroutine
    def recv_into(self, data, size):
        return (yield SYSCALL_SOCKET_RECV_INTO, self._socket, data, size)

    @coroutine
    def send(self, data):
        return (yield SYSCALL_SOCKET_SEND, self._socket, data)


class TcpServerSocket(SocketBase):
    CAN_BE_CLIENT = False
    CAN_BE_SERVER = True

    def __init__(self, socket_obj):
        super().__init__(socket_obj=socket_obj)

    @coroutine
    def recv(self, size):
        return (yield SYSCALL_SOCKET_RECV, self._socket, size)

    @coroutine
    def recv_into(self, data, size):
        return (yield SYSCALL_SOCKET_RECV_INTO, self._socket, data, size)

    @coroutine
    def send(self, data):
        return (yield SYSCALL_SOCKET_SEND, self._socket, data)


class TcpListenSocket(SocketBase):
    def __init__(self, version=4):
        super().__init__(socket_family=_IP_FAMILY[version], socket_type=SOCK_STREAM, socket_protocol=IPPROTO_TCP)

    def bind(self, addr):
        self._socket.bind(addr)

    @coroutine
    def accept(self, nursery, handler_factory):
        return (yield SYSCALL_SOCKET_ACCEPT, self._socket, nursery, TcpServerSocket, handler_factory)

    @coroutine
    def listen(self, backlog):
        return (yield SYSCALL_SOCKET_LISTEN, self._socket, backlog)


class UnixClientSocket(SocketBase):
    CAN_BE_CLIENT = True
    CAN_BE_SERVER = False

    def __init__(self):
        super().__init__(socket_family=AF_UNIX, socket_type=SOCK_STREAM, socket_protocol=0)

    def bind(self, addr):
        self._socket.bind(addr)

    @coroutine
    def connect(self, addr):
        return (yield SYSCALL_SOCKET_CONNECT, self._socket, addr)

    @coroutine
    def recv(self, size):
        return (yield SYSCALL_SOCKET_RECV, self._socket, size)

    @coroutine
    def recv_into(self, data, size):
        return (yield SYSCALL_SOCKET_RECV_INTO, self._socket, data, size)

    @coroutine
    def send(self, data):
        return (yield SYSCALL_SOCKET_SEND, self._socket, data)


class UnixServerSocket(SocketBase):
    CAN_BE_CLIENT = False
    CAN_BE_SERVER = True

    def __init__(self, socket_obj):
        super().__init__(socket_obj=socket_obj)

    @coroutine
    def recv(self, size):
        return (yield SYSCALL_SOCKET_RECV, self._socket, size)

    @coroutine
    def recv_into(self, data, size):
        return (yield SYSCALL_SOCKET_RECV_INTO, self._socket, data, size)

    @coroutine
    def send(self, data):
        return (yield SYSCALL_SOCKET_SEND, self._socket, data)


class UnixListenSocket(SocketBase):
    def __init__(self):
        super().__init__(socket_family=AF_UNIX, socket_type=SOCK_STREAM, socket_protocol=0)

    def bind(self, addr):
        try:
            unlink(addr)
        except FileNotFoundError:
            if path.exists(addr):
                raise

        self._socket.bind(addr)

    @coroutine
    def accept(self, nursery, handler_factory):
        return (yield SYSCALL_SOCKET_ACCEPT, self._socket, nursery, UnixServerSocket, handler_factory)

    @coroutine
    def listen(self, backlog):
        return (yield SYSCALL_SOCKET_LISTEN, self._socket, backlog)


class TlsSocket:
    __slots__ = '_socket', '_incoming', '_outgoing', '_object'

    def __init__(self, sock, context, server_hostname):
        self._socket = sock
        self._incoming = MemoryBIO()
        self._outgoing = MemoryBIO()
        self._object = context.wrap_bio(
            self._incoming,
            self._outgoing,
            server_hostname=server_hostname,
            server_side=sock.CAN_BE_SERVER)

    async def handshake(self):
        while True:
            try:
                self._object.do_handshake()

                return
            except SSLWantReadError:
                if self._outgoing.pending:
                    await self._socket.send(self._outgoing.read())

                self._incoming.write(await self._socket.recv(4096))
            except SSLWantWriteError:
                if self._outgoing.pending:
                    await self._socket.send(self._outgoing.read())

    async def recv(self, size):
        while True:
            try:
                return self._object.read(size)
            except SSLWantReadError:
                if self._outgoing.pending:
                    await self._socket.send(self._outgoing.read())

                data = await self._socket.recv(size)
                self._incoming.write(data)
            except SSLWantWriteError:
                if self._outgoing.pending:
                    await self._socket.send(self._outgoing.read())

    async def recv_into(self, data, size):
        while True:
            try:
                return self._object.read(size, data)
            except SSLWantReadError:
                if self._outgoing.pending:
                    await self._socket.send(self._outgoing.read())

                data = await self._socket.recv(size)
                self._incoming.write(data)
            except SSLWantWriteError:
                if self._outgoing.pending:
                    await self._socket.send(self._outgoing.read())

    async def send(self, data):
        while True:
            try:
                return self._object.write(data)
            except SSLWantReadError:
                if self._outgoing.pending:
                    await self._socket.send(self._outgoing.read())

                data = await self._socket.recv(4096)
                self._incoming.write(data)
            except SSLWantWriteError:
                if self._outgoing.pending:
                    await self._socket.send(self._outgoing.read())

    async def close(self):
        while True:
            try:
                return self._object.unwrap()
            except SSLWantReadError:
                if self._outgoing.pending:
                    await self._socket.send(self._outgoing.read())

                self._incoming.write(await self._socket.recv(4096))
            except SSLWantWriteError:
                if self._outgoing.pending:
                    await self._socket.send(self._outgoing.read())


SOCKET_KIND_UNKNOWN = '?'
SOCKET_KIND_SERVER_LISTENING = 'L'
SOCKET_KIND_SERVER_CONNECTION = 'S'
SOCKET_KIND_CLIENT_CONNECTION = 'C'


class _SocketInfo:
    __slots__ = \
        'fileno', \
        'kind', \
        'frame', \
        'recv_task_info', 'send_task_info', \
        'recv_ready', 'send_ready', \
        'event_mask'

    def __init__(self, fileno):
        # Socket descriptor.
        self.fileno = fileno
        # Socket kind.
        self.kind = SOCKET_KIND_UNKNOWN
        # Task which waits for socket to become readable. \
        # Does not necessary mean task wants to call recv* family function.
        self.recv_task_info = None
        # Task which waits for socket to become writable. \
        # Does not necessary mean task wants to call send* family function.
        self.send_task_info = None
        # True if socket became readable when no task was waiting for it to become readable; otherwise False.
        self.recv_ready = False
        # True if socket became writable when no task was waiting for it to become writable; otherwise False.
        self.send_ready = False
        # Event mask of currently awaited events.
        self.event_mask = 0


class _SelectFakeEPoll:
    __slots__ = '_rlist', '_wlist', '_xlist', '_fdict'

    def __init__(self):
        self._rlist = []
        self._wlist = []
        self._xlist = []
        self._fdict = defaultdict(int)

    def register(self, fileno, eventmask):
        self.modify(fileno, eventmask)

    def unregister(self, fileno):
        self.modify(fileno, 0)

    def modify(self, fileno, eventmask):
        eventmask = eventmask & 0x_0005 # EPOLLIN | # EPOLLOUT
        old_eventmask = self._fdict[fileno]

        if old_eventmask == 0 and eventmask != 0:
            self._xlist.append(fileno)

        if old_eventmask != 0 and eventmask == 0:
            self._xlist.remove(fileno)

        if (old_eventmask ^ eventmask) & 0x_0001 == 0x_0001: # EPOLLIN
            # Read event mask changed

            if old_eventmask & 0x_0001 == 0x_0001:
                # Must stop reading
                self._rlist.remove(fileno)
            else:
                # Must start reading
                self._rlist.append(fileno)

        if (old_eventmask ^ eventmask) & 0x_0004 == 0x_0004: # EPOLLOUT
            # Write event mask changed

            if old_eventmask & 0x_0004 == 0x_0004:
                # Must stop writing
                self._wlist.remove(fileno)
            else:
                # Must start writing
                self._wlist.append(fileno)

        self._fdict[fileno] = eventmask

    def poll(self, timeout):
        from select import select

        rlist, wlist, xlist = select(self._rlist, self._wlist, self._xlist, timeout)

        events = defaultdict(int)

        for fileno in rlist:
            events[fileno] |= 0x_0001 # EPOLLIN

        for fileno in wlist:
            events[fileno] |= 0x_0004 # EPOLLOUT

        for fileno in xlist:
            events[fileno] |= 0x_0008 # EPOLLERR

        return events.items()
