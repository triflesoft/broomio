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


class TaskAbortError(BaseException):
    pass


class Nursery(object):
    def __init__(self, exception_policy=NurseryExceptionPolicy.Abort):
        self._children = set()
        self._watchers = set()
        self._exception_policy = exception_policy
        self._exceptions = []

    async def __aenter__(self):
        # Nothing to do here.
        return self

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
