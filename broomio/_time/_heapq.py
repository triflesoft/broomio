from time import sleep as time_sleep
from heapq import heappop


class LoopTimeHeapQ(object):
    def __init__(self):
        self._info = None

    def _process_time_heapq(self):
        # First task in queue.
        moment, task_info = self._info.time_heapq[0]

        # Is task scheduled to run later?
        if moment >= self._info.now + 0.001:
            # Do not wait too much, ler loop cycle.
            timeout = moment - self._info.now

            if timeout > 0.01:
                time_sleep(0.01)
            else:
                time_sleep(timeout)

                # Run all tasks which are ready to run.
                while (len(self._info.time_heapq) > 0) and (moment >= self._info.time_heapq[0][0]):
                    _, task_info = heappop(self._info.time_heapq)
                    self._info.task_deque.append(task_info)

            del timeout

        del task_info
        del moment