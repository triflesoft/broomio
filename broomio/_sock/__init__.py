from .._syscalls import SYSCALL_SOCKET_ACCEPT
from .._syscalls import SYSCALL_SOCKET_CLOSE
from .._syscalls import SYSCALL_SOCKET_CONNECT
from .._syscalls import SYSCALL_SOCKET_RECV
from .._syscalls import SYSCALL_SOCKET_RECV_INTO
from .._syscalls import SYSCALL_SOCKET_RECVFROM
from .._syscalls import SYSCALL_SOCKET_RECVFROM_INTO
from .._syscalls import SYSCALL_SOCKET_SEND
from .._syscalls import SYSCALL_SOCKET_SENDTO
from .._syscalls import SYSCALL_SOCKET_SHUTDOWN
from socket import AF_INET
from socket import AF_INET6
from socket import IPPROTO_TCP
from socket import IPPROTO_UDP
from socket import SO_REUSEADDR
from socket import SO_REUSEPORT
from socket import SOCK_DGRAM
from socket import SOCK_STREAM
from socket import SOL_SOCKET
from types import coroutine


_SOCKET_KINDS = {
    'tcp4': (AF_INET,  SOCK_STREAM, IPPROTO_TCP),
    'udp4': (AF_INET,  SOCK_DGRAM,  IPPROTO_UDP),
    'tcp6': (AF_INET6, SOCK_STREAM, IPPROTO_TCP),
    'udp6': (AF_INET6, SOCK_STREAM, IPPROTO_UDP),
}


class socket(object):
    def __init__(self, kind_name='tcp4', sock=None):
        from socket import socket as _socket

        kind = _SOCKET_KINDS[kind_name]

        if sock is None:
            self._socket = _socket(kind[0], kind[1], kind[2])
            self._socket.setblocking(0)
        else:
            self._socket = sock

    def __get_reuse_addr(self):
        return bool(self._socket.getsockopt(SOL_SOCKET, SO_REUSEADDR))

    def __set_reuse_addr(self, value):
        return self._socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1 if value else 0)

    def __get_reuse_port(self):
        return bool(self._socket.getsockopt(SOL_SOCKET, SO_REUSEPORT))

    def __set_reuse_port(self, value):
        return self._socket.setsockopt(SOL_SOCKET, SO_REUSEPORT, 1 if value else 0)

    reuse_addr = property(__get_reuse_addr, __set_reuse_addr)
    reuse_port = property(__get_reuse_port, __set_reuse_port)

    def bind(self, addr):
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
        self._socket.listen(backlog)

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
