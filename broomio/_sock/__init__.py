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
from os import strerror
from socket import AF_INET
from socket import AF_INET6
from socket import IPPROTO_TCP
from socket import IPPROTO_UDP
from socket import SO_ERROR
from socket import SOCK_DGRAM
from socket import SOCK_STREAM
from socket import SOL_SOCKET
from types import coroutine


def _get_socket_exception(socket):
    code = socket.getsockopt(SOL_SOCKET, SO_ERROR)
    text = strerror(code)

    return OSError(code, text)


_SOCKET_KINDS = {
    'tcp4': (AF_INET,  SOCK_STREAM, IPPROTO_TCP),
    'udp4': (AF_INET,  SOCK_DGRAM,  IPPROTO_UDP),
    'tcp6': (AF_INET6, SOCK_STREAM, IPPROTO_TCP),
    'udp6': (AF_INET6, SOCK_DGRAM,  IPPROTO_UDP),
}

class socket(object):
    __slots__ = '_socket', '_opt_reuse_addr', '_opt_reuse_port', 'reuse_addr', 'reuse_port'

    def __get_socket_opt_null(self):
        return False

    def __set_socket_opt_null(self, value):
        pass

    def __get_socket_opt_addr(self):
        return bool(self._socket.getsockopt(SOL_SOCKET, self._opt_reuse_addr))

    def __set_socket_opt_addr(self, value):
        self._socket.setsockopt(SOL_SOCKET, self._opt_reuse_addr, 1 if value else 0)

    def __get_socket_opt_port(self):
        return bool(self._socket.getsockopt(SOL_SOCKET, self._opt_reuse_port))

    def __set_socket_opt_port(self, value):
        self._socket.setsockopt(SOL_SOCKET, self._opt_reuse_port, 1 if value else 0)

    def __init__(self, kind_name='tcp4', sock=None):
        from socket import socket as _socket

        kind = _SOCKET_KINDS[kind_name]

        if sock is None:
            self._socket = _socket(kind[0], kind[1], kind[2])
            self._socket.setblocking(False)
        else:
            self._socket = sock

        try:
            from socket import SO_REUSEADDR

            self._opt_reuse_addr = SO_REUSEADDR
            self.reuse_addr = property(self.__get_socket_opt_addr, self.__set_socket_opt_addr)
        except (ImportError, ModuleNotFoundError):
            self.reuse_addr = property(self.__get_socket_opt_null, self.__set_socket_opt_null)

        try:
            from socket import SO_REUSEPORT

            self._opt_reuse_port = SO_REUSEPORT
            self.reuse_port = property(self.__get_socket_opt_port, self.__set_socket_opt_port)
        except (ImportError, ModuleNotFoundError):
            self.reuse_port = property(self.__get_socket_opt_null, self.__set_socket_opt_null)

    def getpeername(self):
        return self._socket.getpeername()

    def getsockname(self):
        return self._socket.getsockname()

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
