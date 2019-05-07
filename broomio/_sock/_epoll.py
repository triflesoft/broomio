from . import _get_socket_exception_from_fileno
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
        assert socket_info.kind == SOCKET_KIND_SERVER_LISTENING, \
            f'Internal data structures are damaged for socket #{socket_info.fileno} ({socket_info.kind}).'

        sock, nursery, socket_factory, handler_factory = task_info.yield_args
        # Extract parent coroutine call chain frames.
        stack_frames = _get_coro_stack_frames(task_info.coro)

        try:
            while True:
                client_socket, client_address = sock.accept()
                client_socket_info = self._get_sock_info(client_socket.fileno())

                # pylint: disable=C0301
                assert client_socket_info.kind == SOCKET_KIND_UNKNOWN, \
                    f'Internal data structures are damaged for socket #{client_socket_info.fileno} ({client_socket_info.kind}). Most probably previous connection with the same file number was not properly closed.'

                client_socket.setblocking(False)
                client_socket_info.kind = SOCKET_KIND_SERVER_CONNECTION
                handler = handler_factory(socket_factory(socket_obj=client_socket), client_address)
                child_task_info = self._task_create_new(handler, task_info, stack_frames, nursery) # pylint: disable=E1101
                self._task_enqueue_one(child_task_info)
        except OSError:
            pass

        self._task_enqueue_one(task_info)

    def _sock_send(self, task_info, socket_info):
        # pylint: disable=C0301
        assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), \
            f'Internal data structures are damaged for socket #{socket_info.fileno} ({socket_info.kind}).'

        sock, data = task_info.yield_args

        try:
            size = sock.send(data)
            task_info.send_args = size
        except OSError as os_error:
            task_info.throw_exc = os_error

        self._task_enqueue_one(task_info)

    def _sock_sendto(self, task_info, socket_info):
        # pylint: disable=C0301
        assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), \
            f'Internal data structures are damaged for socket #{socket_info.fileno} ({socket_info.kind}).'

        sock, data, addr = task_info.yield_args

        try:
            size = sock.sendto(data, addr)
            task_info.send_args = size
        except OSError as os_error:
            task_info.throw_exc = os_error

        self._task_enqueue_one(task_info)

    def _sock_recv(self, task_info, socket_info):
        # pylint: disable=C0301
        assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), \
            f'Internal data structures are damaged for socket #{socket_info.fileno} ({socket_info.kind}).'

        sock, size = task_info.yield_args

        try:
            data = sock.recv(size)
            task_info.send_args = data
        except OSError as os_error:
            task_info.throw_exc = os_error

        self._task_enqueue_one(task_info)

    def _sock_recv_into(self, task_info, socket_info):
        # pylint: disable=C0301
        assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), \
            f'Internal data structures are damaged for socket #{socket_info.fileno} ({socket_info.kind}).'

        sock, data, size = task_info.yield_args

        try:
            size = sock.recv_into(data, size)
            task_info.send_args = size
        except OSError as os_error:
            task_info.throw_exc = os_error

        self._task_enqueue_one(task_info)

    def _sock_recvfrom(self, task_info, socket_info):
        # pylint: disable=C0301
        assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), \
            f'Internal data structures are damaged for socket #{socket_info.fileno} ({socket_info.kind}).'

        sock, size = task_info.yield_args

        try:
            data, addr = sock.recvfrom(size)
            task_info.send_args = data, addr
        except OSError as os_error:
            task_info.throw_exc = os_error

        self._task_enqueue_one(task_info)

    def _sock_recvfrom_into(self, task_info, socket_info):
        # pylint: disable=C0301
        assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), \
            f'Internal data structures are damaged for socket #{socket_info.fileno} ({socket_info.kind}).'

        sock, data, size = task_info.yield_args

        try:
            size, addr = sock.recvfrom_into(data, size)
            task_info.send_args = size, addr
        except OSError as os_error:
            task_info.throw_exc = os_error

        self._task_enqueue_one(task_info)

    def _sock_shutdown(self, task_info, socket_info):
        # pylint: disable=C0301
        assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), \
            f'Internal data structures are damaged for socket #{socket_info.fileno} ({socket_info.kind}).'

        sock, how = task_info.yield_args

        try:
            sock.shutdown(how)
        except OSError as os_error:
            task_info.throw_exc = os_error

        self._task_enqueue_one(task_info)

    def _sock_close(self, task_info, socket_info):
        # pylint: disable=C0301
        assert socket_info.event_mask == 0, \
            f'Internal data structures are damaged for socket #{socket_info.fileno} ({socket_info.kind}).'

        sock = task_info.yield_args[0]

        sock.close()
        socket_info.kind = SOCKET_KIND_UNKNOWN
        socket_info.recv_ready = False
        socket_info.send_ready = False

        self._task_enqueue_one(task_info)

    def _epoll_register(self, socket_info, event_mask):
        # Find all bits in new event mask, which are not present in old event mask. \
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
        # Find all bits in new event mask, which are also present in old event mask. \
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
            # There are unclosed sockets. Use the following code to debug \
            # import tracemalloc \
            # tracemalloc.start(10)
            # pylint: disable=C0301
            raise RuntimeWarning('Unclosed sockets with no tasks awaiting them detected. Enable tracemalloc to get the socket allocation traceback.')

        # If any tasks are scheduled to be run later, do not make them late; otherwise wait for 5 second. \
        # FIXME: Justify timeout value, currently 5 seconds.
        if self._time_heapq:
            timeout = self._time_heapq[0][0] - self._now
        else:
            if self._pool_task_count > 0:
                timeout = 0.001
            else:
                timeout = 5

        events = self._socket_epoll.poll(timeout)

        for fileno, event in events:
            socket_info = self._get_sock_info(fileno)

            if (event & 0x_0008) == 0x_0008: # EPOLLERR
                # Socket failed.
                self._epoll_unregister(socket_info, 0x_0005) # EPOLLIN | EPOLLOUT

                # Get exception.
                exception = _get_socket_exception_from_fileno(fileno)

                # Enqueue throwing exception.
                if socket_info.send_task_info:
                    socket_info.send_task_info.send_fileno = None
                    socket_info.send_task_info.throw_exc = exception
                    self._task_enqueue_one(socket_info.send_task_info)
                    socket_info.send_task_info = None
                    self._socket_task_count -= 1

                # Enqueue throwing exception.
                if socket_info.recv_task_info:
                    socket_info.recv_task_info.recv_fileno = None
                    socket_info.recv_task_info.throw_exc = exception
                    self._task_enqueue_one(socket_info.recv_task_info)
                    socket_info.recv_task_info = None
                    self._socket_task_count -= 1

                del exception
            else:
                if (event & 0x_0001) == 0x_0001: # EPOLLIN
                    # Socket is readable.
                    task_info = socket_info.recv_task_info

                    if task_info is None:
                        # No task awaits for socket to become readable. Mark as readale.
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
                        # No task awaits for socket to become writable. Mark as writable.
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

                            self._sock_close(task_info, socket_info)
                        elif task_info.yield_func == SYSCALL_SOCKET_CONNECT:
                            # Connect.
                            sock, addr = task_info.yield_args
                            # Connection complete.
                            self._task_enqueue_one(task_info)

                            socket_info.kind = SOCKET_KIND_CLIENT_CONNECTION

                            del addr
                            del sock
                        elif task_info.yield_func == SYSCALL_SOCKET_SEND:
                            self._sock_send(task_info, socket_info)
                        elif task_info.yield_func == SYSCALL_SOCKET_SENDTO:
                            self._sock_sendto(task_info, socket_info)
                        elif task_info.yield_func == SYSCALL_SOCKET_SHUTDOWN:
                            self._sock_shutdown(task_info, socket_info)
                        else:
                            raise Exception(f'Unexpected syscall {task_info.yield_func}.')

            del socket_info

        return True
