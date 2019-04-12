from ._sock import socket
from ._sock import SOCKET_KIND_CLIENT_CONNECTION
from ._sock import SOCKET_KIND_SERVER_CONNECTION
from ._sock import SOCKET_KIND_SERVER_LISTENING
from ._sock import SOCKET_KIND_UNKNOWN
from ._sock._epoll import LoopSockEpoll
from ._task import _TaskInfo
from ._task import Nursery
from ._task import NurseryError
from ._task import NurseryExceptionPolicy
from ._task._deque import LoopTaskDeque
from ._time import sleep
from ._time._heapq import LoopTimeHeapQ
from ._util import _get_coro_stack_frames
from heapq import heappush
from sys import _getframe
from time import time


__all__ = ['Loop', 'Nursery', 'NurseryError', 'NurseryExceptionPolicy', 'sleep', 'socket']


class Loop(LoopTaskDeque, LoopSockEpoll, LoopTimeHeapQ):
    def _task_enqueue_new(self, coro, parent_task_info, stack_frames, parent_nursery):
        child_task_info = _TaskInfo(coro, parent_task_info, stack_frames, parent_nursery)
        parent_nursery._children.add(child_task_info)
        self._task_enqueue_old(child_task_info)

    def _task_enqueue_new_delay(self, coro, parent_task_info, stack_frames, parent_nursery, delay):
        child_task_info = _TaskInfo(coro, parent_task_info, stack_frames, parent_nursery)
        parent_nursery._children.add(child_task_info)
        heappush(self._time_heapq, (self._now + delay, child_task_info))

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

        if len(self._task_nursery._exceptions) > 0:
            raise NurseryError(self._task_nursery._exceptions) from self._task_nursery._exceptions[0][1]
