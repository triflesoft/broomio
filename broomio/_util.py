from ._sock import _SelectFakeEPoll
from ._sock import _SocketInfo
from ._task import Nursery
from collections import deque


def _get_coro_stack_frames(coro):
    stack_frames = []

    while True:
        cr_frame = getattr(coro, 'cr_frame', None)

        if not cr_frame:
            break

        stack_frames.append(cr_frame)
        coro = getattr(coro, 'cr_await', None)

    return stack_frames


class _LoopSlots(object):
    __slots__ = \
        '_info', \
        '_task_deque', '_task_nursery', \
        '_task_enqueue_old', \
        '_time_heapq', '_now', \
        '_sock_array', '_get_sock_info', '_socket_wait_count', '_socket_task_count', '_socket_epoll'

    def __init__(self, technology=None):
        # Deque with tasks ready to be executed.
        # These are new tasks or tasks for which requested syscall completed.
        self._task_deque = deque()

        # SPEED: Much faster than declaring method, which calls method.
        # SPEED:
        # SPEED: def _task_enqueue_old(self, task_info): # THIS IS SLOW
        # SPEED:     self._task_deque.append(task_info)  # THIS IS SLOW
        # SPEED:

        # TODO: justify determinism
        #self._task_enqueue_old = self._task_deque.append if int(time()) % 2 == 0 else self._task_deque.appendleft
        self._task_enqueue_old = self._task_deque.append

        # Root nursery.
        self._task_nursery = Nursery()

        # HeapQ with tasks scheduled to run later.9o
        self._time_heapq = []
        self._now = 0

        try:
            # For Linux: \
            # Array of sockets. Indexes in list are file descriptors. O(1) access time.
            # Why can we do this? Man page socket(2) states:
            #     The file descriptor returned by a successful call will be \
            #     the lowest-numbered file descriptor not currently open for the process.
            # While some indexes will not be used, for instance 0, 1, and 2, because \
            # they will correspond to file descriptors opened by different means, we \
            # still may assume values of file descriptors to be small integers.
            from resource import getrlimit
            from resource import RLIMIT_NOFILE

            _, nofile_hard = getrlimit(RLIMIT_NOFILE)
            self._sock_array = [_SocketInfo(fileno) for fileno in range(nofile_hard)]
        except:
            # For Windows \
            # Dict of sockets. Keys in dict are file descriptors. O(log(N)) access time.
            # No assumptions about socket file descriptor values' range \
            # can possibly be deducted from MSDN.
            class _SocketDict(dict):
                def __missing__(self, fileno):
                    socket_info = _SocketInfo(fileno)
                    self[fileno] = socket_info

                    return socket_info

            self._sock_array = _SocketDict()

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
        # TODO: Support IOCP.
        # TODO: Support kqueue.

        if technology:
            technologies = [technology, 'epoll', 'iocp', 'kqueue', 'poll', 'select']
        else:
            technologies = ['epoll', 'iocp', 'kqueue', 'poll']

        self._socket_epoll = None

        for technology in technologies:
            if technology == 'epoll':
                try:
                    from select import epoll

                    self._socket_epoll = epoll(1024)
                    break
                except ImportError:
                    pass
            elif technology == 'poll':
                try:
                    from select import poll

                    self._socket_epoll = poll()
                    break
                except ImportError:
                    pass
            elif technology == 'select':
                self._socket_epoll = _SelectFakeEPoll()
                break

        if not self._socket_epoll:
            self._socket_epoll = _SelectFakeEPoll()
