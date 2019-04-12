from .._syscalls import SYSCALL_NURSERY_INIT
from .._syscalls import SYSCALL_NURSERY_JOIN
from .._syscalls import SYSCALL_NURSERY_KILL
from .._syscalls import SYSCALL_NURSERY_START_LATER
from .._syscalls import SYSCALL_NURSERY_START_SOON
from enum import Enum
from types import coroutine


class NurseryExceptionPolicy(Enum):
    Abort = 1
    Accumulate = 2
    Ignore = 3


class NurseryError(Exception):
    def __init__(self, exceptions):
        self.exceptions = exceptions

    def __repr__(self):
        return str(self)

    def __str__(self):
        return ''.join(
            f'\n\t{repr(exception[1])} @ {repr(exception[0].coro.cr_code)}' for exception in self.exceptions)


class Nursery(object):
    def __init__(self, exception_policy=NurseryExceptionPolicy.Abort, timeout=-1):
        self._children = set()
        self._watchers = set()
        self._exception_policy = exception_policy
        self._exceptions = []
        self._timeout = timeout
        self._task_info = None

    @coroutine
    def __aenter__(self):
        # Create new nursery
        return (yield SYSCALL_NURSERY_INIT, self)

    @coroutine
    def __aexit__(self, exception_type, exception, traceback):
        if exception_type is None:
            # Wait for all nursery tasks to be finished.
            return (yield SYSCALL_NURSERY_JOIN, self)
        else:
            # Cancel all nursery tasks.
            return (yield SYSCALL_NURSERY_KILL, self, exception_type, exception, traceback)

    @coroutine
    def start_soon(self, coro):
        if self._exceptions:
            raise NurseryError(self._exceptions) from self._exceptions[0][1]

        return (yield SYSCALL_NURSERY_START_SOON, self, coro)

    @coroutine
    def start_later(self, coro, delay):
        if self._exceptions:
            raise NurseryError(self._exceptions) from self._exceptions[0][1]

        return (yield SYSCALL_NURSERY_START_LATER, self, coro, delay)


class _TaskInfo(object):
    __slots__ = \
        'coro', \
        'yield_func', 'yield_args', \
        'send_args', 'throw_exc', \
        'parent_task_info', 'stack_frames', \
        'recv_fileno', 'send_fileno', \
        'parent_nursery', 'child_nursery'

    def __init__(self, coro, parent_task_info, stack_frames, parent_nursery):
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
        # Parent task, the one from which nursery.start_soon or nursery.start_later was called.
        self.parent_task_info = parent_task_info
        # Stack frames.
        self.stack_frames = stack_frames
        # Socket descriptor for which task is waiting to become readable.
        # Only one of recv_fileno and send_fileno may be set.
        self.recv_fileno = None
        # Socket descriptor for which task is waiting to become writable.
        # Only one of recv_fileno and send_fileno may be set.
        self.send_fileno = None
        # Nursery to which this task belongs.
        self.parent_nursery = parent_nursery
        # Nursery created from this task.
        self.child_nursery = None

    def __lt__(self, other):
        return id(self) < id(other)

    def __le__(self, other):
        return id(self) <= id(other)

    def __eq__(self, other):
        return id(self) == id(other)

    def __ne__(self, other):
        return id(self) != id(other)

    def __gt__(self, other):
        return id(self) > id(other)

    def __ge__(self, other):
        return id(self) >= id(other)

    def __hash__(self):
        return id(self)

