from ._sock import socket
from ._util import _get_coro_stack_frames
from heapq import heappush


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
SOCKET_KIND_UNKNOWN           = 0x_00
SOCKET_KIND_SERVER_LISTENING  = 0x_11
SOCKET_KIND_SERVER_CONNECTION = 0x_12
SOCKET_KIND_CLIENT_CONNECTION = 0x_22

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
        from collections import defaultdict

        self._rlist = []
        self._wlist = []
        self._xlist = []
        self._fdict = defaultdict(int)

    def register(self, fd, eventmask):
        self.modify(fd, eventmask)

    def unregister(self, fd):
        self.modify(fd, 0)

    def modify(self, fd, eventmask):
        old_eventmask = self._fdict[fd]

        if old_eventmask != eventmask:
            pass

    def poll(self, timeout):
        from select import select

        rlist, wlist, xlist = select(self._rlist, self._wlist, self._xlist, timeout)
