from ._info import _LoopInfo
from ._info import SOCKET_KIND_CLIENT_CONNECTION
from ._info import SOCKET_KIND_SERVER_CONNECTION
from ._info import SOCKET_KIND_SERVER_LISTENING
from ._info import SOCKET_KIND_UNKNOWN
from ._sock import socket
from ._sock._epoll import LoopSockEpoll
from ._task import Nursery
from ._task._deque import LoopTaskDeque
from ._time import sleep
from ._time._heapq import LoopTimeHeapQ
from ._util import _get_coro_stack_frames
from sys import _getframe
from time import time
from traceback import print_exc


__all__ = ['Loop', 'Nursery', 'sleep', 'socket']


class Loop(LoopTaskDeque, LoopSockEpoll, LoopTimeHeapQ):
    def _sock_accept(self, task_info, socket_info):
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

    def _sock_send(self, task_info, socket_info):
        assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), 'Internal data structures are damaged.'
        # Send data.
        sock, data = task_info.yield_args
        size = sock.send(data)
        # Enqueue task.
        task_info.send_args = size
        self._info.task_enqueue_old(task_info)

    def _sock_sendto(self, task_info, socket_info):
        assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), 'Internal data structures are damaged.'
        # Send data.
        sock, data, addr = task_info.yield_args
        size = sock.sendto(data, addr)
        # Enqueue task.
        task_info.send_args = size
        self._info.task_enqueue_old(task_info)

    def _sock_recv(self, task_info, socket_info):
        assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), 'Internal data structures are damaged.'
        # Receive data.
        sock, size = task_info.yield_args
        data = sock.recv(size)
        # Enqueue task.
        task_info.send_args = data
        self._info.task_enqueue_old(task_info)

    def _sock_recv_into(self, task_info, socket_info):
        assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), 'Internal data structures are damaged.'
        # Receive data.
        sock, data, size = task_info.yield_args
        size = sock.recv_into(data, size)
        # Enqueue task.
        task_info.send_args = size
        self._info.task_enqueue_old(task_info)

    def _sock_recvfrom(self, task_info, socket_info):
        assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), 'Internal data structures are damaged.'
        # Receive data.
        sock, size = task_info.yield_args
        data, addr = sock.recvfrom(size)
        # Enqueue task.
        task_info.send_args = data, addr
        self._info.task_enqueue_old(task_info)

    def _sock_recvfrom_into(self, task_info, socket_info):
        assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), 'Internal data structures are damaged.'
        # Receive data.
        sock, data, size = task_info.yield_args
        size, addr = sock.recvfrom_into(data, size)
        # Enqueue task.
        task_info.send_args = size, addr
        self._info.task_enqueue_old(task_info)

    def _sock_close(self, sock, socket_info):
        sock.close()
        socket_info.kind = SOCKET_KIND_UNKNOWN
        socket_info.recv_ready = False
        socket_info.send_ready = False
        socket_info.event_mask = 0

    def _sock_epoll_modify(self, socket_info):
        if socket_info.event_mask == 0:
            self._info.socket_epoll.unregister(socket_info.fileno)
        else:
            self._info.socket_epoll.modify(socket_info.fileno, socket_info.event_mask)

        self._info.socket_wait_count -= 1

    def _sock_epoll_unregister(self, socket_info):
        # Close socket.
        # Is socket registered for reading notification?
        if socket_info.event_mask & 0x_0001 == 0x_0001: # EPOLLIN
            self._info.socket_wait_count -= 1

        # Is socket registered for writing notification?
        if socket_info.event_mask & 0x_0004 == 0x_0004: # EPOLLOUT
            self._info.socket_wait_count -= 1

        self._info.socket_epoll.unregister(socket_info.fileno)

    def __init__(self, technology=None):
        self._info = _LoopInfo(Nursery(), int(time()) % 2 == 0, technology)

    def start_soon(self, coro):
        # Create task info for root task. Root tasks have no parent.
        # Root tasks can be created after loop was started from \
        # another thread, but that does not look like great idea.
        stack_frames = []

        # Extract method call chain frames.
        # Skip one stack frame corresponding to Loop.start_soon method.
        for frame_index in range(1, 256):
            try:
                stack_frames.append(_getframe(frame_index))
            except ValueError:
                break

        self._info.task_enqueue_new(coro, None, reversed(stack_frames), self._info.task_nursery)

    def run(self):
        # True if there are any tasks scheduled.
        running = True

        while running:
            # Each loop iteration is a tick.
            # Current time as reference for timers.
            self._info.now = time()

            # SPEED: Testing if collection is empty before calling method is much faster.
            # SPEED: If collection is empty, method is not called.

            # Are there tasks ready for execution?
            if len(self._info.task_deque) > 0:
                self._process_task()
            # Are there task which are scheduled to run later?
            elif len(self._info.time_heapq) > 0:
                self._process_time()
            # Are there sockets to check for readiness?
            elif self._info.socket_wait_count > 0:
                self._process_sock()
            else:
                # Nothing to do, stop loop.
                running = False


