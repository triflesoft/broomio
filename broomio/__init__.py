from ._info import _TaskInfo
from ._info import _SocketInfo
from ._info import _SelectFakeEPoll
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
from heapq import heappush
from sys import _getframe
from time import time
from traceback import print_exc


__all__ = ['Loop', 'Nursery', 'sleep', 'socket']


class Loop(LoopTaskDeque, LoopSockEpoll, LoopTimeHeapQ):
    __slots__ = \
        '_info', \
        '_task_deque', '_task_nursery', \
        '_task_enqueue_old', \
        '_time_heapq', '_now', \
        '_sock_array', '_socket_wait_count', '_socket_task_count', '_socket_epoll' \

    def _task_enqueue_new(self, coro, parent_task_info, stack_frames, nursery):
        child_task_info = _TaskInfo(coro, parent_task_info, stack_frames, nursery)
        nursery._children.add(child_task_info)
        self._task_enqueue_old(child_task_info)

    def _task_enqueue_new_delay(self, coro, parent_task_info, stack_frames, nursery, delay):
        child_task_info = _TaskInfo(coro, parent_task_info, stack_frames, nursery)
        nursery._children.add(child_task_info)
        heappush(self._time_heapq, (self._now + delay, child_task_info))

    def _sock_accept(self, task_info, socket_info):
        assert socket_info.kind == SOCKET_KIND_SERVER_LISTENING, 'Internal data structures are damaged.'
        # Accept as many connections as possible.
        sock, nursery, handler_factory = task_info.yield_args
        # Extract parent coroutine call chain frames.
        stack_frames = _get_coro_stack_frames(task_info.coro)

        try:
            while True:
                client_socket, client_address = sock.accept()
                client_socket_info = self._get_sock_info(client_socket.fileno())
                assert client_socket_info.kind == SOCKET_KIND_UNKNOWN, 'Internal data structures are damaged.'
                client_socket_info.kind = SOCKET_KIND_SERVER_CONNECTION
                handler = handler_factory(socket(sock=client_socket), client_address)
                self._task_enqueue_new(handler, task_info, stack_frames, nursery)
        except OSError:
            pass

        self._task_enqueue_old(task_info)

    def _sock_send(self, task_info, socket_info):
        assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), 'Internal data structures are damaged.'
        # Send data.
        sock, data = task_info.yield_args
        size = sock.send(data)
        # Enqueue task.
        task_info.send_args = size
        self._task_enqueue_old(task_info)

    def _sock_sendto(self, task_info, socket_info):
        assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), 'Internal data structures are damaged.'
        # Send data.
        sock, data, addr = task_info.yield_args
        size = sock.sendto(data, addr)
        # Enqueue task.
        task_info.send_args = size
        self._task_enqueue_old(task_info)

    def _sock_recv(self, task_info, socket_info):
        assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), 'Internal data structures are damaged.'
        # Receive data.
        sock, size = task_info.yield_args
        data = sock.recv(size)
        # Enqueue task.
        task_info.send_args = data
        self._task_enqueue_old(task_info)

    def _sock_recv_into(self, task_info, socket_info):
        assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), 'Internal data structures are damaged.'
        # Receive data.
        sock, data, size = task_info.yield_args
        size = sock.recv_into(data, size)
        # Enqueue task.
        task_info.send_args = size
        self._task_enqueue_old(task_info)

    def _sock_recvfrom(self, task_info, socket_info):
        assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), 'Internal data structures are damaged.'
        # Receive data.
        sock, size = task_info.yield_args
        data, addr = sock.recvfrom(size)
        # Enqueue task.
        task_info.send_args = data, addr
        self._task_enqueue_old(task_info)

    def _sock_recvfrom_into(self, task_info, socket_info):
        assert (socket_info.kind == SOCKET_KIND_SERVER_CONNECTION) or (socket_info.kind == SOCKET_KIND_CLIENT_CONNECTION), 'Internal data structures are damaged.'
        # Receive data.
        sock, data, size = task_info.yield_args
        size, addr = sock.recvfrom_into(data, size)
        # Enqueue task.
        task_info.send_args = size, addr
        self._task_enqueue_old(task_info)

    def _sock_close(self, sock, socket_info):
        sock.close()
        socket_info.kind = SOCKET_KIND_UNKNOWN
        socket_info.recv_ready = False
        socket_info.send_ready = False
        assert socket_info.event_mask == 0, 'Internal data structures are damaged.'

    def _epoll_register(self, socket_info, event_mask):
        event_mask_diff = socket_info.event_mask ^ event_mask

        if event_mask_diff > 0:
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
        event_mask_diff = socket_info.event_mask & event_mask

        if event_mask_diff > 0:
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

    def __init__(self, technology=None):
        from collections import deque
        from resource import getrlimit
        from resource import RLIMIT_NOFILE

        _, nofile_hard = getrlimit(RLIMIT_NOFILE)

        # Deque with tasks ready to be executed.
        # These are new tasks or tasks for which requested syscall completed.
        self._task_deque = deque()

        # SPEED: Much faster than declaring method, which calls method.
        # SPEED:
        # SPEED: def _task_enqueue_old(self, task_info): # THIS IS SLOW
        # SPEED:     self._task_deque.append(task_info)  # THIS IS SLOW
        # SPEED:

        # Also, task order is randomized
        self._task_enqueue_old = self._task_deque.append if int(time()) % 2 == 0 else self._task_deque.appendleft

        # Root nursery.
        self._task_nursery = Nursery()

        # HeapQ with tasks scheduled to run later.9o
        self._time_heapq = []
        self._now = 0

        # For Linux: \
        # Array of sockets. Indexes in list are file descriptors. O(1) access time.
        # Why can we do this? Man page socket(2) states:
        #     The file descriptor returned by a successful call will be \
        #     the lowest-numbered file descriptor not currently open for the process.
        # While some indexes will not be used, for instance 0, 1, and 2, because \
        # they will correspond to file descriptors opened by different means, we \
        # still may assume values of file descriptors to be small integers.
        # For Windows \
        # Dict of sockets. Keys in dict are file descriptors. O(log(N)) access time.
        # No assumptions about socket file descriptor values' range \
        # can possibly be deducted from MSDN.
        self._sock_array = [_SocketInfo(fileno) for fileno in range(nofile_hard)]

        # SPEED: Much faster than declaring method, which calls method.
        # SPEED:
        # SPEED: def _get_sock_info(self, fileno):   # THIS IS SLOW
        # SPEED:     return self._sock_array[fileno] # THIS IS SLOW
        # SPEED:
        self._get_sock_info = self._sock_array.__getitem__

        # Number of sockets waiting to become readable or writable.
        # If socket is awaited to become readable and writable, it will be counted twice.
        self._socket_wait_count = 0

        # Number of task awaiting for sockets to become readable or writable.
        self._socket_task_count = 0

        # Event polling is Linux specific for _now.
        # TODO: Support select.
        # TODO: Support IOCP.
        # TODO: Support kqueue.

        if technology:
            technologies = [technology, 'epoll', 'iocp', 'kqueue', 'poll', 'select']
        else:
            technologies = ['epoll', 'iocp', 'kqueue', 'poll']

        for technology in technologies:
            if technology == 'epoll':
                try:
                    from select import epoll

                    self._socket_epoll = epoll(1024)
                    break
                except ModuleNotFoundError:
                    pass
            elif technology == 'poll':
                try:
                    from select import poll

                    self._socket_epoll = poll()
                    break
                except ModuleNotFoundError:
                    pass
            elif technology == 'select':
                self._socket_epoll = _SelectFakeEPoll()
                break

        if not self._socket_epoll:
            self._socket_epoll = _SelectFakeEPoll()


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

        self._task_enqueue_new(coro, None, reversed(stack_frames), self._task_nursery)

    def run(self):
        # True if there are any tasks scheduled.
        running = True

        while running:
            # Each loop iteration is a tick.
            # Current time as reference for timers.
            self._now = time()

            # SPEED: Testing if collection is empty before calling method is much faster.
            # SPEED: If collection is empty, method is not called.

            # Are there tasks ready for execution?
            if len(self._task_deque) > 0:
                self._process_task()
            # Are there task which are scheduled to run later?
            elif len(self._time_heapq) > 0:
                self._process_time()
            # Are there sockets to check for readiness?
            elif self._socket_wait_count > 0:
                self._process_sock()
            else:
                # Nothing to do, stop loop.
                running = False


