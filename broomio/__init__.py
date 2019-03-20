from ._info import _LoopInfo
from ._info import _TaskInfo
from ._sock import socket
from ._sock._epoll import LoopSockEpoll
from ._task import Nursery
from ._task._deque import LoopTaskDeque
from ._time import sleep
from ._time._heapq import LoopTimeHeapQ
from time import time
from traceback import print_exc


__all__ = ['Loop', 'Nursery', 'sleep', 'socket']


class Loop(LoopTaskDeque, LoopSockEpoll, LoopTimeHeapQ):
    def __init__(self):
        self._info = _LoopInfo(Nursery())

    def start_soon(self, coro):
        # Create task info for root task. Root tasks have no parent.
        # Root tasks can be created after loop was started from \
        # another thread, but that does not look like great idea.
        task_info = _TaskInfo(coro, None, self._info.task_nursery)
        # Don't forget to add task to root nursery.
        self._info.task_nursery._children.add(task_info)
        # And also enqueue task.
        self._info.task_deque.append(task_info)

    def run(self):
        # True if there are any tasks scheduled.
        running = True

        while running:
            # Each loop iteration is a tick.
            try:
                # Current time as reference for timers.
                self._info.now = time()

                # Are there tasks ready for execution?
                if len(self._info.task_deque) > 0:
                    self._process_task_deque()
                # Are there sockets to check for readiness?
                elif self._info.socket_recv_count + self._info.socket_send_count > 0:
                    self._process_sock_array()
                # Are there task which are scheduled to run later?
                elif len(self._info.time_heapq) > 0:
                    self._process_time_heapq()
                else:
                    # Nothing to do, stop loop.
                    running = False
            except Exception:
                print_exc()


