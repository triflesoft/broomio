from . import _get_socket_exception
from .._sock import socket
from .._sock import SOCKET_KIND_CLIENT_CONNECTION
from .._sock import SOCKET_KIND_SERVER_CONNECTION
from .._sock import SOCKET_KIND_SERVER_LISTENING
from .._sock import SOCKET_KIND_UNKNOWN
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
from .._util import _get_coro_stack_frames
from .._util import _LoopSlots


class LoopSockEpoll(_LoopSlots):
    def _sock_accept(self, task_info, socket_info):
        assert socket_info.kind == SOCKET_KIND_SERVER_LISTENING, f'Internal data structures are damaged for socket #{socket_info.fileno} ({socket_info.kind}).'
        # Accept as many connections as possible.
        sock, nursery, handler_factory = task_info.yield_args
        # Extract parent coroutine call chain frames.
        stack_frames = _get_coro_stack_frames(task_info.coro)

        try:
            while True:
                client_socket, client_address = sock.accept()
                client_socket_info = self._get_sock_info(client_socket.fileno())
                assert client_socket_info.kind == SOCKET_KIND_UNKNOWN, f'Internal data structures are damaged for socket #{socket_info.fileno} ({socket_info.kind}).'
                client_socket_info.kind = SOCKET_KIND_SERVER_CONNECTION
                handler = handler_factory(socket(sock=client_socket), client_address)
                self._task_enqueue_new(handler, task_info, stack_frames, nursery)
        except OSError:
            pass

        self._task_enqueue_old(task_info)

    def _sock_send(self, task_info, socket_info):
        assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), f'Internal data structures are damaged for socket #{socket_info.fileno} ({socket_info.kind}).'
        # Send data.
        sock, data = task_info.yield_args
        size = sock.send(data)
        # Enqueue task.
        task_info.send_args = size
        self._task_enqueue_old(task_info)

    def _sock_sendto(self, task_info, socket_info):
        assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), f'Internal data structures are damaged for socket #{socket_info.fileno} ({socket_info.kind}).'
        # Send data.
        sock, data, addr = task_info.yield_args
        size = sock.sendto(data, addr)
        # Enqueue task.
        task_info.send_args = size
        self._task_enqueue_old(task_info)

    def _sock_recv(self, task_info, socket_info):
        assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), f'Internal data structures are damaged for socket #{socket_info.fileno} ({socket_info.kind}).'
        # Receive data.
        sock, size = task_info.yield_args
        data = sock.recv(size)
        # Enqueue task.
        task_info.send_args = data
        self._task_enqueue_old(task_info)

    def _sock_recv_into(self, task_info, socket_info):
        assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), f'Internal data structures are damaged for socket #{socket_info.fileno} ({socket_info.kind}).'
        # Receive data.
        sock, data, size = task_info.yield_args
        size = sock.recv_into(data, size)
        # Enqueue task.
        task_info.send_args = size
        self._task_enqueue_old(task_info)

    def _sock_recvfrom(self, task_info, socket_info):
        assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), f'Internal data structures are damaged for socket #{socket_info.fileno} ({socket_info.kind}).'
        # Receive data.
        sock, size = task_info.yield_args
        data, addr = sock.recvfrom(size)
        # Enqueue task.
        task_info.send_args = data, addr
        self._task_enqueue_old(task_info)

    def _sock_recvfrom_into(self, task_info, socket_info):
        assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), f'Internal data structures are damaged for socket #{socket_info.fileno} ({socket_info.kind}).'
        # Receive data.
        sock, data, size = task_info.yield_args
        size, addr = sock.recvfrom_into(data, size)
        # Enqueue task.
        task_info.send_args = size, addr
        self._task_enqueue_old(task_info)

    def _sock_close(self, sock, socket_info):
        assert socket_info.event_mask == 0, f'Internal data structures are damaged for socket #{socket_info.fileno} ({socket_info.kind}).'
        sock.close()
        socket_info.kind = SOCKET_KIND_UNKNOWN
        socket_info.recv_ready = False
        socket_info.send_ready = False

    def _epoll_register(self, socket_info, event_mask):
        # Find all bits in new event mask, which are not present in old event mask
        # In other words find all 0,1 combinations.
        event_mask_diff = ~socket_info.event_mask & event_mask

        if event_mask_diff != 0:
            if event_mask_diff & 0x_0001 == 0x_0001: # EPOLLIN
                self._socket_wait_count += 1

            if event_mask_diff & 0x_0004 == 0x_0004: # EPOLLOUT
                self._socket_wait_count += 1

            if socket_info.event_mask == 0:
                socket_info.event_mask = event_mask
                self._socket_epoll.register(socket_info.fileno, 0x_2018 | socket_info.event_mask)
            else:
                socket_info.event_mask |= event_mask
                self._socket_epoll.modify(socket_info.fileno, 0x_2018 | socket_info.event_mask)

    def _epoll_unregister(self, socket_info, event_mask):
        # Find all bits in new event mask, which are also present in old event mask
        # In other words find all 1,1 combinations.
        event_mask_diff = socket_info.event_mask & event_mask

        if event_mask_diff != 0:
            if event_mask_diff & 0x_0001 == 0x_0001: # EPOLLIN
                self._socket_wait_count -= 1

            if event_mask_diff & 0x_0004 == 0x_0004: # EPOLLOUT
                self._socket_wait_count -= 1

            if socket_info.event_mask == event_mask_diff:
                socket_info.event_mask = 0
                self._socket_epoll.unregister(socket_info.fileno)
            else:
                socket_info.event_mask &= ~event_mask
                self._socket_epoll.modify(socket_info.fileno, 0x_2018 | socket_info.event_mask)

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
