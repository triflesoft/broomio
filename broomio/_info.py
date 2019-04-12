from ._sock import socket
from ._task import Nursery
from collections import defaultdict
from collections import deque


#
# Task information.
#
class _TaskInfo(object):
    __slots__ = \
        'coro', \
        'yield_func', 'yield_args', \
        'send_args', 'throw_exc', \
        'parent_task_info', 'stack_frames', \
        'recv_fileno', 'send_fileno', \
        'nursery'

    def __init__(self, coro, parent_task_info, stack_frames, nursery):
        # Coroutine to be executed.
        self.coro = coro
        # Syscall function coroutine requested.
        self.yield_func = None
        # Syscall arguments coroutine requested.
        self.yield_args = None
        # Result of last syscall to be passed to coroutine.
        self.send_args = None
        # Exception to be passed to coroutine.
        self.throw_exc = None
        # Parent task, the one from which nursery.start_soon nursery.start_later was called.
        self.parent_task_info = parent_task_info
        # Stack frames.
        self.stack_frames = stack_frames
        # Socket descriptor for which task is waiting to become readable.
        # Only one of recv_fileno and send_fileno may be set.
        self.recv_fileno = None
        # Socket descriptor for which task is waiting to become writable.
        # Only one of recv_fileno and send_fileno may be set.
        self.send_fileno = None
        # Nursery to which task belongs.
        self.nursery = nursery


#
# Socket information.
#
SOCKET_KIND_UNKNOWN           = '?'
SOCKET_KIND_SERVER_LISTENING  = 'L'
SOCKET_KIND_SERVER_CONNECTION = 'S'
SOCKET_KIND_CLIENT_CONNECTION = 'C'

class _SocketInfo(object):
    __slots__ = \
        'fileno', \
        'kind', \
        'frame', \
        'recv_task_info', 'send_task_info', \
        'recv_ready', 'send_ready', \
        'event_mask'

    def __init__(self, fileno):
        # Socket descriptor.
        self.fileno = fileno
        # Socket kind.
        self.kind = SOCKET_KIND_UNKNOWN
        # Task which waits for socket to become readable.
        # Does not necessary mean task wants to call recv* family function.
        self.recv_task_info = None
        # Task which waits for socket to become writable.
        # Does not necessary mean task wants to call send* family function.
        self.send_task_info = None
        # True if socket became readable when no task was waiting for it \
        # to become readable; otherwise False.
        self.recv_ready = False
        # True if socket became writable when no task was waiting for it \
        # to become writable; otherwise False.
        self.send_ready = False
        # Event mask of currently awaited events.
        self.event_mask = 0


class _SelectFakeEPoll(object):
    __slots__ = '_rlist', '_wlist', '_xlist', '_fdict'

    def __init__(self):
        self._rlist = []
        self._wlist = []
        self._xlist = []
        self._fdict = defaultdict(int)

    def register(self, fd, eventmask):
        self.modify(fd, eventmask)

    def unregister(self, fd):
        self.modify(fd, 0)

    def modify(self, fd, eventmask):
        eventmask = eventmask & 0x_0005 # EPOLLIN | # EPOLLOUT
        old_eventmask = self._fdict[fd]

        if old_eventmask == 0 and eventmask != 0:
            self._xlist.append(fd)

        if old_eventmask != 0 and eventmask == 0:
            self._xlist.remove(fd)

        if (old_eventmask ^ eventmask) & 0x_0001 == 0x_0001: # EPOLLIN
            # Read event mask changed

            if old_eventmask & 0x_0001 == 0x_0001:
                # Must stop reading
                self._rlist.remove(fd)
            else:
                # Must start reading
                self._rlist.append(fd)

        if (old_eventmask ^ eventmask) & 0x_0004 == 0x_0004: # EPOLLOUT
            # Write event mask changed

            if old_eventmask & 0x_0004 == 0x_0004:
                # Must stop writing
                self._wlist.remove(fd)
            else:
                # Must start writing
                self._wlist.append(fd)

        self._fdict[fd] = eventmask

    def poll(self, timeout):
        from select import select

        rlist, wlist, xlist = select(self._rlist, self._wlist, self._xlist, timeout)

        events = defaultdict(int)

        for fd in rlist:
            events[fd] |= 0x_0001 # EPOLLIN

        for fd in wlist:
            events[fd] |= 0x_0004 # EPOLLOUT

        for fd in xlist:
            events[fd] |= 0x_0008 # EPOLLERR

        return events.items()


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
