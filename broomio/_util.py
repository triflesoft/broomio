from collections import deque
from random import randint
from ._sock import _SelectFakeEPoll
from ._sock import _SocketInfo
from ._task import Nursery


def _get_coro_stack_frames(coro):
    stack_frames = []

    while True:
        cr_frame = getattr(coro, 'cr_frame', None)

        if not cr_frame:
            break

        stack_frames.append(cr_frame)
        coro = getattr(coro, 'cr_await', None)

    return stack_frames


class _LoopSlots:
    __slots__ = \
        '_info', \
        '_task_deque', '_task_nursery', \
        '_task_enqueue_one', \
        '_task_enqueue_many', \
        '_time_heapq', '_now', \
        '_sock_array', '_get_sock_info', '_socket_wait_count', '_socket_task_count', '_socket_epoll', \
        '_pool_queue_map', '_pool_task_count'

    def _task_enqueue_many_fifo(self, *task_infos):
        for task_info in task_infos:
            self._task_deque.appendleft(task_info)

    def _task_enqueue_many_lifo(self, *task_infos):
        for task_info in reversed(task_infos):
            self._task_deque.append(task_info)

    def __init__(self, technology=None, execution_order=None):
        # Deque with tasks ready to be executed. These are new tasks or tasks for which requested syscall completed.
        self._task_deque = deque()

        # Task execution order cannot be deterministic, because we do not want to keep unintended assumptions hidden
        # until some unrelated refactoring breaks expected task execution order and introduces Mandelbug. Task execution
        # order should not be assumed in any way. However truly random execution order is not acceptable either, since
        # inserting task in the middle of any general purpose data structure: stack, array, queue, or linked list is not
        # O(1) and thus too expensive. Thus, implemented practical decision is to make execution order either FIFO or
        # LIFO on random. However this is not end of story. There are special cases of Nursery.start_soon and
        # Nursery.start_later. These syscalls enqueue two tasks: parent and child. Nursery.start_soon always enqueues
        # two tasks and Nursery.start_later may enqueue two tasks if delay is zero or less. No matter what task
        # execution order was choosen, to make Nursery machinery work correctly parent should countinue execution before
        # child starts execution. Otherwise multiple children may throw exceptions which will not be properly processed.
        # Tasks are always dequeued by popping from right. So deque.appendleft should be used for FIFO and deque.append
        # should be used for LIFO.
        if not execution_order:
            execution_order = 'FIFO' if (randint(0, 1) == 0) else 'LIFO'

        assert execution_order in ('FIFO', 'LIFO'), 'Value of execution_order must be either "FIFO" or "LIFO".'

        if execution_order == 'FIFO':
            # SPEED: Much faster than declaring method, which calls method. \
            # SPEED: def _task_enqueue_one(self, task_info): # THIS IS SLOW \
            # SPEED:     self._task_deque.append(task_info)  # THIS IS SLOW \
            self._task_enqueue_one = self._task_deque.appendleft
            self._task_enqueue_many = self._task_enqueue_many_fifo
        else:
            # SPEED: Much faster than declaring method, which calls method. \
            # SPEED: def _task_enqueue_one(self, task_info): # THIS IS SLOW \
            # SPEED:     self._task_deque.append(task_info)  # THIS IS SLOW \
            self._task_enqueue_one = self._task_deque.append
            self._task_enqueue_many = self._task_enqueue_many_lifo

        # Root nursery.
        self._task_nursery = Nursery()

        # HeapQ with tasks scheduled to run later.9o
        self._time_heapq = []
        self._now = 0

        try:
            # For Linux: \
            # Array of sockets. Indexes in list are file descriptors. O(1) access time. \
            # Why can we do this? Man page socket(2) states: \
            #     The file descriptor returned by a successful call will be \
            #     the lowest-numbered file descriptor not currently open for the process. \
            # While some indexes will not be used, for instance 0, 1, and 2, because \
            # they will correspond to file descriptors opened by different means, we \
            # still may assume values of file descriptors to be small integers.
            from resource import getrlimit
            from resource import RLIMIT_NOFILE

            _, nofile_hard = getrlimit(RLIMIT_NOFILE)
            self._sock_array = [_SocketInfo(fileno) for fileno in range(nofile_hard)]
        except ImportError:
            # For Windows: \
            # Dict of sockets. Keys in dict are file descriptors. O(log(N)) access time. \
            # No assumptions about socket file descriptor values' range \
            # can possibly be deducted from MSDN.
            class _SocketDict(dict):
                def __missing__(self, fileno):
                    socket_info = _SocketInfo(fileno)
                    self[fileno] = socket_info

                    return socket_info

            self._sock_array = _SocketDict()

        # SPEED: Much faster than declaring method, which calls method. \
        # SPEED: def _get_sock_info(self, fileno):   # THIS IS SLOW \
        # SPEED:     return self._sock_array[fileno] # THIS IS SLOW
        self._get_sock_info = self._sock_array.__getitem__

        # Number of sockets waiting to become readable or writable. \
        # If socket is awaited to become readable and writable, it will be counted twice.
        self._socket_wait_count = 0

        # Number of tasks awaiting for sockets to become readable or writable.
        self._socket_task_count = 0

        # Event polling is effective on Linux only for now. \
        # TODO: Support IOCP. \
        # TODO: Support kqueue. \
        # The major difference betweel select/poll/epoll (S/P/E) and kqueue/IOCP (K/I) is that \
        # S/P/E tells when operation can be performed and K/I tells when previous operation \
        # completed. Thus to support K/I either entire _epoll.py should be rewritten as \
        # _iocp.py/_kqueue.py introducing addtional complexity and inevitable bugs or S/P/E \
        # logic should be emulated with K/I. Emulating looks possible if we assume that less \
        # than N pending operations logically equals readyness to perform one more operation. \
        # Who knows if that's true statement at all?

        if technology:
            technologies = [technology, 'epoll', 'iocp', 'kqueue', 'poll', 'select']
        else:
            technologies = ['epoll', 'iocp', 'kqueue', 'poll']

        self._socket_epoll = None

        for tech in technologies:
            if tech == 'epoll':
                try:
                    from select import epoll

                    self._socket_epoll = epoll(1024)
                    break
                except ImportError:
                    pass
            elif tech == 'poll':
                try:
                    from select import poll

                    self._socket_epoll = poll()
                    break
                except ImportError:
                    pass
            elif tech == 'select':
                self._socket_epoll = _SelectFakeEPoll()
                break

        if not self._socket_epoll:
            self._socket_epoll = _SelectFakeEPoll()

        self._pool_queue_map = {}
        self._pool_task_count = 0
