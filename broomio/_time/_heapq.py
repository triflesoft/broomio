from .._task import _TaskInfo
from .._task import Nursery
from .._util import _LoopSlots
from heapq import heappop
from time import sleep as time_sleep


class LoopTimeHeapQ(_LoopSlots):
    def _process_time(self):
        # First task in queue.
        moment, _, _ = self._time_heapq[0]

        # Is task scheduled to run later?
        if self._now < moment:
            # If there is any socket activity, better wait in epoll.
            if self._socket_wait_count > 0:
                return

            time_sleep(moment - self._now)

        # Run all tasks which are ready to run.
        while (len(self._time_heapq) > 0) and (self._now >= self._time_heapq[0][0]):
            _, operation, element = heappop(self._time_heapq)

            if operation == 0x_01:
                self._task_enqueue_one(element)
            elif operation == 0x_02:
                if type(element) is _TaskInfo:
                    self._task_abort(element)
                elif type(element) is Nursery:
                    self._nursery_abort_children(element)
                else:
                    assert False, 'Unexpected time heapq element.'
            else:
                assert False, 'Unexpected time heapq operation.'

        return True
