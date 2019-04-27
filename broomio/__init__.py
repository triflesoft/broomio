from ._sock import TcpClientSocket
from ._sock import TcpListenSocket
from ._sock import TlsSocket
from ._sock import UdpSocket
from ._sock import UnixClientSocket
from ._sock import UnixListenSocket
from ._sock._epoll import LoopSockEpoll
from ._task import Nursery
from ._task import NurseryError
from ._task import NurseryExceptionPolicy
from ._task._deque import LoopTaskDeque
from ._time import sleep
from ._time._heapq import LoopTimeHeapQ
from sys import _getframe
from time import time


__all__ = [
    'Loop', 'Nursery', 'NurseryError', 'NurseryExceptionPolicy',
    'sleep',
    'TcpClientSocket', 'TcpListenSocket', 'TlsSocket', 'UdpSocket', 'UnixClientSocket', 'UnixListenSocket']


class Loop(LoopTaskDeque, LoopSockEpoll, LoopTimeHeapQ):
    def start_soon(self, coro):
        # Create task info for root task. Root tasks have no parent. Root tasks can be created after loop was started \
        # from another thread, but that does not look like great idea.
        stack_frames = []

        # Extract method call chain frames. Skip one stack frame corresponding to Loop.start_soon method.
        for frame_index in range(1, 256):
            try:
                stack_frames.append(_getframe(frame_index))
            except ValueError:
                break

        self._task_enqueue_one(
            self._task_create_new(coro, None, reversed(stack_frames), self._task_nursery))

    def run(self):
        # True if there are any tasks scheduled.
        running = True

        while running:
            # Each loop iteration is a tick. Current time as reference for timers.
            self._now = time()

            # SPEED: Testing if collection is empty before calling method is much faster. \
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
