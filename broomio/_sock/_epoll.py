from . import _get_socket_exception
from . import socket
from .._info import SOCKET_KIND_CLIENT_CONNECTION
from .._info import SOCKET_KIND_SERVER_CONNECTION
from .._info import SOCKET_KIND_SERVER_LISTENING
from .._info import SOCKET_KIND_UNKNOWN
from .._info import _LoopSlots
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


class LoopSockEpoll(_LoopSlots):
    def _process_sock(self):
        if self._socket_task_count == 0:
            # There are unclosed sockets.
            # Use the following code to debug
            #
            # import tracemalloc
            #
            # tracemalloc.start(10)

            raise RuntimeWarning('Unclosed sockets with no tasks awaiting them detected. Enable tracemalloc to get the socket allocation traceback.')

        # If any tasks are scheduled to be run later, do not make them late.
        # Otherwise wait for 5 second.
        # TODO: Justify timeout value, currently 5 seconds.
        timeout = self._time_heapq[0][0] - self._now if len(self._time_heapq) > 0 else 5
        events = self._socket_epoll.poll(timeout)

        for fileno, event in events:
            socket_info = self._get_sock_info(fileno)

            if (event & 0x_0008) == 0x_0008: # EPOLLERR
                # Socket failed.
                self._epoll_unregister(socket_info, 0x_0005) # EPOLLIN | EPOLLOUT

                # Get socket.
                if socket_info.send_task_info:
                    sock = socket_info.send_task_info.yield_args[0]
                elif socket_info.recv_task_info:
                    sock = socket_info.recv_task_info.yield_args[0]

                # Get exception.
                exception = _get_socket_exception(sock)

                # Enqueue throwing exception.
                if socket_info.send_task_info:
                    socket_info.send_task_info.send_fileno = None
                    socket_info.send_task_info.throw_exc = exception
                    self._task_enqueue_old(socket_info.send_task_info)
                    socket_info.send_task_info = None
                    self._socket_task_count -= 1

                # Enqueue throwing exception.
                if socket_info.recv_task_info:
                    socket_info.recv_task_info.recv_fileno = None
                    socket_info.recv_task_info.throw_exc = exception
                    self._task_enqueue_old(socket_info.recv_task_info)
                    socket_info.recv_task_info = None
                    self._socket_task_count -= 1

                self._sock_close(sock, socket_info)

                del exception
                del sock
            else:
                if (event & 0x_0001) == 0x_0001: # EPOLLIN
                    # Socket is readable.
                    task_info = socket_info.recv_task_info

                    if task_info is None:
                        # No task awaits for socket to become readable.
                        # Mark as readale.
                        socket_info.recv_ready = True

                        self._epoll_unregister(socket_info, 0x_0001) # EPOLLIN
                    else:
                        # Unbind task and socket.
                        task_info.recv_fileno = None
                        socket_info.recv_task_info = None
                        self._socket_task_count -= 1

                        if task_info.yield_func == SYSCALL_SOCKET_ACCEPT:
                            self._sock_accept(task_info, socket_info)
                        elif task_info.yield_func == SYSCALL_SOCKET_RECV:
                            self._sock_recv(task_info, socket_info)
                        elif task_info.yield_func == SYSCALL_SOCKET_RECV_INTO:
                            self._sock_recv_into(task_info, socket_info)
                        elif task_info.yield_func == SYSCALL_SOCKET_RECVFROM:
                            self._sock_recvfrom(task_info, socket_info)
                        elif task_info.yield_func == SYSCALL_SOCKET_RECVFROM_INTO:
                            self._sock_recvfrom_into(task_info, socket_info)
                        else:
                            raise Exception(f'Unexpected syscall {task_info.yield_func}.')

                if (event & 0x_0004) == 0x_0004: # EPOLLOUT
                    # Socket is writable.
                    task_info = socket_info.send_task_info

                    if task_info is None:
                        # No task awaits for socket to become writable.
                        # Mark as writable.
                        socket_info.send_ready = True

                        self._epoll_unregister(socket_info, 0x_0004) # EPOLLOUT
                    else:
                        # Unbind task and socket.
                        task_info.send_fileno = None
                        socket_info.send_task_info = None
                        self._socket_task_count -= 1

                        if task_info.yield_func == SYSCALL_SOCKET_CLOSE:
                            # Close socket.
                            self._epoll_unregister(socket_info, 0x_0005) # EPOLLIN | EPOLLOUT

                            if socket_info.recv_task_info:
                                socket_info.recv_task_info.recv_fileno = None
                                socket_info.recv_task_info = None
                                self._socket_task_count -= 1

                            sock = task_info.yield_args[0]

                            self._sock_close(sock, socket_info)
                            self._task_enqueue_old(task_info)

                            del sock
                        elif task_info.yield_func == SYSCALL_SOCKET_CONNECT:
                            # Connect.
                            sock, addr = task_info.yield_args
                            # Connection complete.
                            self._task_enqueue_old(task_info)

                            socket_info.kind = SOCKET_KIND_CLIENT_CONNECTION

                            del addr
                            del sock
                        elif task_info.yield_func == SYSCALL_SOCKET_SEND:
                            self._sock_send(task_info, socket_info)
                        elif task_info.yield_func == SYSCALL_SOCKET_SENDTO:
                            self._sock_sendto(task_info, socket_info)
                        elif task_info.yield_func == SYSCALL_SOCKET_SHUTDOWN:
                            # TODO: SYSCALL_SOCKET_SHUTDOWN is not implemented yet.
                            pass
                        else:
                            raise Exception(f'Unexpected syscall {task_info.yield_func}.')
            del socket_info

        return True
