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
            # Wait for childred to complete.
            return (yield SYSCALL_NURSERY_JOIN, self)
        else:
            # Kill all childred.
            # TODO: SYSCALL_NURSERY_KILL is not implemented yet.
            return (yield SYSCALL_NURSERY_KILL, self, exception_type, exception, traceback)

    @coroutine
    def start_soon(self, coro):
        if self._exceptions:
            raise NurseryError(self._exceptions)

        return (yield SYSCALL_NURSERY_START_SOON, self, coro)

    @coroutine
    def start_later(self, coro, delay):
        if self._exceptions:
            raise NurseryError(self._exceptions)

        return (yield SYSCALL_NURSERY_START_LATER, self, coro, delay)
