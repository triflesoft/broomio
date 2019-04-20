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
from collections import defaultdict
from os import path
from os import strerror
from os import unlink
from socket import AF_INET
from socket import AF_INET6
from socket import AF_UNIX
from socket import IPPROTO_TCP
from socket import IPPROTO_UDP
from socket import SO_ERROR
from socket import SOCK_DGRAM
from socket import SOCK_STREAM
from socket import SOL_SOCKET
from socket import SHUT_WR
from struct import calcsize
from struct import unpack
from types import coroutine


def _get_socket_exception(socket):
    code = socket.getsockopt(SOL_SOCKET, SO_ERROR)
    text = strerror(code)

    return OSError(code, text)


_SOCKET_KINDS = {
    'unix': (AF_UNIX,  SOCK_STREAM, -1),
    'tcp4': (AF_INET,  SOCK_STREAM, IPPROTO_TCP),
    'udp4': (AF_INET,  SOCK_DGRAM,  IPPROTO_UDP),
    'tcp6': (AF_INET6, SOCK_STREAM, IPPROTO_TCP),
    'udp6': (AF_INET6, SOCK_DGRAM,  IPPROTO_UDP),
}


class socket(object):
    __slots__ = '_socket', '_kind_name'

    def __get_socket_opt_reuse_addr(self):
        if self._opt_reuse_addr:
            return bool(self._socket.getsockopt(SOL_SOCKET, self._opt_reuse_addr))
        else:
            return False

    def __set_socket_opt_reuse_addr(self, value):
        if self._opt_reuse_addr:
            self._socket.setsockopt(SOL_SOCKET, self._opt_reuse_addr, 1 if value else 0)

    def __get_socket_opt_reuse_port(self):
        if self._opt_reuse_port:
            return bool(self._socket.getsockopt(SOL_SOCKET, self._opt_reuse_port))
        else:
            return False

    def __set_socket_opt_reuse_port(self, value):
        if self._opt_reuse_port:
            self._socket.setsockopt(SOL_SOCKET, self._opt_reuse_port, 1 if value else 0)

    def __get_socket_opt_peer_cred(self):
        if self._opt_peer_cred:
            # FIXME: pid, uid, gid order may not be respected by non-Linux *nixes.
            credentials = self._socket.getsockopt(SOL_SOCKET, self._opt_peer_cred, calcsize("3i"))

            return unpack("3i", credentials)

    reuse_addr = property(__get_socket_opt_reuse_addr, __set_socket_opt_reuse_addr)
    reuse_port = property(__get_socket_opt_reuse_port, __set_socket_opt_reuse_port)
    peer_cred = property(__get_socket_opt_peer_cred)

    def __init__(self, kind_name='tcp4', sock=None):
        from socket import socket as _socket

        kind = _SOCKET_KINDS[kind_name]

        self._kind_name = kind_name

        if sock is None:
            self._socket = _socket(kind[0], kind[1], kind[2])
            self._socket.setblocking(False)
        else:
            self._socket = sock

    def getpeername(self):
        return self._socket.getpeername()

    def getsockname(self):
        return self._socket.getsockname()

    def bind(self, addr):
        if self._kind_name == 'unix':
            try:
                unlink(addr)
            except:
                if path.exists(addr):
                    raise

        self._socket.bind(addr)

    @coroutine
    def accept(self, nursery, handler_factory):
        return (yield SYSCALL_SOCKET_ACCEPT, self._socket, nursery, handler_factory)

    @coroutine
    def close(self):
        return (yield SYSCALL_SOCKET_CLOSE, self._socket)

    @coroutine
    def connect(self, addr):
        return (yield SYSCALL_SOCKET_CONNECT, self._socket, addr)

    @coroutine
    def listen(self, backlog):
        return (yield SYSCALL_SOCKET_LISTEN, self._socket, backlog)

    @coroutine
    def recv(self, size):
        return (yield SYSCALL_SOCKET_RECV, self._socket, size)

    @coroutine
    def recv_into(self, data, size):
        return (yield SYSCALL_SOCKET_RECV_INTO, self._socket, data, size)

    @coroutine
    def recvfrom(self, size):
        return (yield SYSCALL_SOCKET_RECVFROM, self._socket, size)

    @coroutine
    def recvfrom_into(self, data, size):
        return (yield SYSCALL_SOCKET_RECVFROM_INTO, self._socket, data, size)

    @coroutine
    def send(self, data):
        return (yield SYSCALL_SOCKET_SEND, self._socket, data)

    @coroutine
    def sendto(self, data, addr):
        return (yield SYSCALL_SOCKET_SENDTO, self._socket, data, addr)

    @coroutine
    def shutdown(self):
        return (yield SYSCALL_SOCKET_SHUTDOWN, self._socket, SHUT_WR)


try:
    from socket import SO_REUSEADDR

    socket._opt_reuse_addr = SO_REUSEADDR
except ImportError:
    socket._opt_reuse_addr = None

try:
    from socket import SO_REUSEPORT

    socket._opt_reuse_port = SO_REUSEPORT
except ImportError:
    socket._opt_reuse_port = None

try:
    # FIXME: Some OSes support SO_PEERCRED while Python's socket module does not export this constant
    # FIXME: They say SO_PEERCRED equals 17 on most x86/x64 Linuxes
    from socket import SO_PEERCRED

    socket._opt_peer_cred = SO_PEERCRED
except ImportError:
    socket._opt_peer_cred = None


SOCKET_KIND_UNKNOWN           = '?'
SOCKET_KIND_SERVER_LISTENING  = 'L'
SOCKET_KIND_SERVER_CONNECTION = 'S'
SOCKET_KIND_CLIENT_CONNECTION = 'C'

class _SocketInfo(object):
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
        # Task which waits for socket to become readable.
        # Does not necessary mean task wants to call recv* family function.
        self.recv_task_info = None
        # Task which waits for socket to become writable.
        # Does not necessary mean task wants to call send* family function.
        self.send_task_info = None
        # True if socket became readable when no task was waiting for it \
        # to become readable; otherwise False.
        self.recv_ready = False
        # True if socket became writable when no task was waiting for it \
        # to become writable; otherwise False.
        self.send_ready = False
        # Event mask of currently awaited events.
        self.event_mask = 0


class _SelectFakeEPoll(object):
    __slots__ = '_rlist', '_wlist', '_xlist', '_fdict'

    def __init__(self):
        self._rlist = []
        self._wlist = []
        self._xlist = []
        self._fdict = defaultdict(int)

    def register(self, fd, eventmask):
        self.modify(fd, eventmask)

    def unregister(self, fd):
        self.modify(fd, 0)

    def modify(self, fd, eventmask):
        eventmask = eventmask & 0x_0005 # EPOLLIN | # EPOLLOUT
        old_eventmask = self._fdict[fd]

        if old_eventmask == 0 and eventmask != 0:
            self._xlist.append(fd)

        if old_eventmask != 0 and eventmask == 0:
            self._xlist.remove(fd)

        if (old_eventmask ^ eventmask) & 0x_0001 == 0x_0001: # EPOLLIN
            # Read event mask changed

            if old_eventmask & 0x_0001 == 0x_0001:
                # Must stop reading
                self._rlist.remove(fd)
            else:
                # Must start reading
                self._rlist.append(fd)

        if (old_eventmask ^ eventmask) & 0x_0004 == 0x_0004: # EPOLLOUT
            # Write event mask changed

            if old_eventmask & 0x_0004 == 0x_0004:
                # Must stop writing
                self._wlist.remove(fd)
            else:
                # Must start writing
                self._wlist.append(fd)

        self._fdict[fd] = eventmask

    def poll(self, timeout):
        from select import select

        rlist, wlist, xlist = select(self._rlist, self._wlist, self._xlist, timeout)

        events = defaultdict(int)

        for fd in rlist:
            events[fd] |= 0x_0001 # EPOLLIN

        for fd in wlist:
            events[fd] |= 0x_0004 # EPOLLOUT

        for fd in xlist:
            events[fd] |= 0x_0008 # EPOLLERR

        return events.items()

