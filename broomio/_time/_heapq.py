from .._info import _LoopSlots
from time import sleep as time_sleep
from heapq import heappop


class LoopTimeHeapQ(_LoopSlots):
    def _process_time(self):
        # First task in queue.
        moment, task_info = self._time_heapq[0]

        # Is task scheduled to run later?
        if self._now < moment:
            # If there is any socket activity, better wait in epoll.
            if self._socket_wait_count > 0:
                return

            time_sleep(moment - self._now)

        # Run all tasks which are ready to run.
        while (len(self._time_heapq) > 0) and (self._now >= self._time_heapq[0][0]):
            _, task_info = heappop(self._time_heapq)
            self._task_enqueue_old(task_info)

        del task_info
        del moment

        return True
