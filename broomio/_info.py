from ._sock import socket
from ._util import _get_coro_stack_frames
from collections import defaultdict
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
