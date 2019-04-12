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
            # TODO: pid, uid, gid order may not be respected by non-Linux *nixes.
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
    def shutdown(self, how):
        return (yield SYSCALL_SOCKET_SHUTDOWN, self._socket, how)


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
    # TODO: Some OSes support SO_PEERCRED while Python's socket module does not export this constant
    # TODO: They say SO_PEERCRED equals 17 on most x86/x64 Linuxes
    from socket import SO_PEERCRED

    socket._opt_peer_cred = SO_PEERCRED
except ImportError:
    socket._opt_peer_cred = None
