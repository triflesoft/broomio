from . import _get_socket_exception
from . import socket
from .._info import SOCKET_KIND_CLIENT_CONNECTION
from .._info import SOCKET_KIND_SERVER_CONNECTION
from .._info import SOCKET_KIND_SERVER_LISTENING
from .._info import SOCKET_KIND_UNKNOWN
from .._util import _get_coro_stack_frames
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

class LoopSockEpoll(object):
    def __init__(self):
        self._info = None

    def _process_sock(self):
        if self._info.socket_task_count == 0:
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
        timeout = self._info.time_heapq[0][0] - self._info.now if len(self._info.time_heapq) > 0 else 5
        events = self._info.socket_epoll.poll(timeout)

        for fileno, event in events:
            socket_info = self._info.sock_array[fileno]

            if (event & 0x_0008) == 0x_0008: # EPOLLERR
                # Socket failed.
                # Close socket.
                # Is socket registered for reading notification?
                if socket_info.event_mask & 0x_0001 == 0x_0001: # EPOLLIN
                    self._info.socket_wait_count -= 1

                # Is socket registered for writing notification?
                if socket_info.event_mask & 0x_0004 == 0x_0004: # EPOLLOUT
                    self._info.socket_wait_count -= 1

                self._info.socket_epoll.unregister(fileno)

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
                    self._info.task_enqueue_old(socket_info.send_task_info)
                    socket_info.send_task_info = None
                    self._info.socket_task_count -= 1

                # Enqueue throwing exception.
                if socket_info.recv_task_info:
                    socket_info.recv_task_info.recv_fileno = None
                    socket_info.recv_task_info.throw_exc = exception
                    self._info.task_enqueue_old(socket_info.send_task_info)
                    socket_info.recv_task_info = None
                    self._info.socket_task_count -= 1

                # Close socket and reset socket info.
                sock.close()
                socket_info.kind = SOCKET_KIND_UNKNOWN
                socket_info.recv_ready = False
                socket_info.send_ready = False
                socket_info.event_mask = 0

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

                        # Note that socket may be registered for writing notification.
                        socket_info.event_mask &= 0x_FFFE # ~0x_0001 EPOLLIN

                        if socket_info.event_mask == 0:
                            self._info.socket_epoll.unregister(fileno)
                        else:
                            self._info.socket_epoll.modify(fileno, socket_info.event_mask)

                        self._info.socket_wait_count -= 1
                    else:
                        # Unbind task and socket.
                        task_info.recv_fileno = None
                        socket_info.recv_task_info = None
                        self._info.socket_task_count -= 1

                        if task_info.yield_func == SYSCALL_SOCKET_ACCEPT:
                            assert socket_info.kind == SOCKET_KIND_SERVER_LISTENING, 'Internal data structures are damaged.'
                            # Accept as many connections as possible.
                            sock, nursery, handler_factory = task_info.yield_args
                            # Extract parent coroutine call chain frames.
                            stack_frames = _get_coro_stack_frames(task_info.coro)

                            try:
                                while True:
                                    client_socket, client_address = sock.accept()
                                    client_socket_info = self._info.sock_array[client_socket.fileno()]
                                    assert client_socket_info.kind == SOCKET_KIND_UNKNOWN, 'Internal data structures are damaged.'
                                    client_socket_info.kind = SOCKET_KIND_SERVER_CONNECTION
                                    handler = handler_factory(socket(sock=client_socket), client_address)
                                    self._info.task_enqueue_new(handler, task_info, stack_frames, nursery)
                            except OSError:
                                pass

                            self._info.task_enqueue_old(task_info)

                            del handler
                            del client_socket_info
                            del client_address
                            del client_socket
                            del handler_factory
                            del nursery
                            del sock
                        elif task_info.yield_func == SYSCALL_SOCKET_RECV:
                            assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), 'Internal data structures are damaged.'
                            # Receive data.
                            sock, size = task_info.yield_args
                            data = sock.recv(size)
                            # Enqueue task.
                            task_info.send_args = data
                            self._info.task_enqueue_old(task_info)

                            del data
                            del size
                            del sock
                        elif task_info.yield_func == SYSCALL_SOCKET_RECV_INTO:
                            assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), 'Internal data structures are damaged.'
                            # Receive data.
                            sock, data, size = task_info.yield_args
                            size = sock.recv_into(data, size)
                            # Enqueue task.
                            task_info.send_args = size
                            self._info.task_enqueue_old(task_info)

                            del data
                            del size
                            del sock
                        elif task_info.yield_func == SYSCALL_SOCKET_RECVFROM:
                            assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), 'Internal data structures are damaged.'
                            # Receive data.
                            sock, size = task_info.yield_args
                            data, addr = sock.recvfrom(size)
                            # Enqueue task.
                            task_info.send_args = data, addr
                            self._info.task_enqueue_old(task_info)

                            del addr
                            del data
                            del size
                            del sock
                        elif task_info.yield_func == SYSCALL_SOCKET_RECVFROM_INTO:
                            assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), 'Internal data structures are damaged.'
                            # Receive data.
                            sock, data, size = task_info.yield_args
                            size, addr = sock.recvfrom_into(data, size)
                            # Enqueue task.
                            task_info.send_args = size, addr
                            self._info.task_enqueue_old(task_info)

                            del addr
                            del size
                            del data
                            del sock
                        else:
                            raise Exception(f'Unexpected syscall {task_info.yield_func}.')

                if (event & 0x_0004) == 0x_0004: # EPOLLOUT
                    # Socket is writable.
                    task_info = socket_info.send_task_info

                    if task_info is None:
                        # No task awaits for socket to become writable.
                        # Mark as writable.
                        socket_info.send_ready = True

                        # Note that socket may be registered for reading notification.
                        socket_info.event_mask &= 0x_FFFB # ~0x_0004 EPOLLOUT

                        if socket_info.event_mask == 0:
                            self._info.socket_epoll.unregister(fileno)
                        else:
                            self._info.socket_epoll.modify(fileno, socket_info.event_mask)

                        self._info.socket_wait_count -= 1
                    else:
                        # Unbind task and socket.
                        task_info.send_fileno = None
                        socket_info.send_task_info = None
                        self._info.socket_task_count -= 1

                        if task_info.yield_func == SYSCALL_SOCKET_CLOSE:
                            # Close socket.
                            # Is socket registered for reading notification?
                            if socket_info.event_mask & 0x_0001 == 0x_0001: # EPOLLIN
                                self._info.socket_wait_count -= 1

                            # Is socket registered for writing notification?
                            if socket_info.event_mask & 0x_0004 == 0x_0004: # EPOLLOUT
                                self._info.socket_wait_count -= 1

                            self._info.socket_epoll.unregister(fileno)

                            sock = task_info.yield_args[0]

                            # Close socket and reset socket info.
                            sock.close()
                            socket_info.kind = SOCKET_KIND_UNKNOWN

                            if socket_info.recv_task_info:
                                socket_info.recv_task_info = None
                                self._info.socket_task_count -= 1

                            socket_info.recv_ready = False
                            socket_info.send_ready = False
                            socket_info.event_mask = 0

                            self._info.task_enqueue_old(task_info)

                            del sock
                        elif task_info.yield_func == SYSCALL_SOCKET_CONNECT:
                            # Connect.
                            sock, addr = task_info.yield_args
                            # Connection complete.
                            self._info.task_enqueue_old(task_info)

                            socket_info.kind = SOCKET_KIND_CLIENT_CONNECTION

                            del addr
                            del sock
                        elif task_info.yield_func == SYSCALL_SOCKET_SEND:
                            assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), 'Internal data structures are damaged.'
                            # Send data.
                            sock, data = task_info.yield_args
                            size = sock.send(data)
                            # Enqueue task.
                            task_info.send_args = size
                            self._info.task_enqueue_old(task_info)

                            del data
                            del size
                        elif task_info.yield_func == SYSCALL_SOCKET_SENDTO:
                            assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), 'Internal data structures are damaged.'
                            # Send data.
                            sock, data, addr = task_info.yield_args
                            size = sock.sendto(data, addr)
                            # Enqueue task.
                            task_info.send_args = size
                            self._info.task_enqueue_old(task_info)

                            del size
                            del addr
                            del data
                            del sock
                        elif task_info.yield_func == SYSCALL_SOCKET_SHUTDOWN:
                            # TODO: SYSCALL_SOCKET_SHUTDOWN is not implemented yet.
                            pass
                        else:
                            raise Exception(f'Unexpected syscall {task_info.yield_func}.')
            del socket_info

        return True

