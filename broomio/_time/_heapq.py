from time import sleep as time_sleep
from heapq import heappop


class LoopTimeHeapQ(object):
    def __init__(self):
        self._info = None

    def _process_time(self):
        # First task in queue.
        moment, task_info = self._info.time_heapq[0]

        # Is task scheduled to run later?
        if self._info.now < moment:
            # If there is any socket activity, better wait in epoll.
            if self._info.socket_wait_count > 0:
                return

            time_sleep(moment - self._info.now)

        # Run all tasks which are ready to run.
        while (len(self._info.time_heapq) > 0) and (self._info.now >= self._info.time_heapq[0][0]):
            _, task_info = heappop(self._info.time_heapq)
            self._info.task_enqueue_old(task_info)

        del task_info
        del moment

        return True

