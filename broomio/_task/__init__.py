from .._syscalls import SYSCALL_NURSERY_JOIN
from .._syscalls import SYSCALL_NURSERY_KILL
from .._syscalls import SYSCALL_NURSERY_START_AFTER
from .._syscalls import SYSCALL_NURSERY_START_SOON
from types import coroutine


class Nursery(object):
    def __init__(self):
        self._children = set()
        self._watchers = set()

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
        return (yield SYSCALL_NURSERY_START_SOON, self, coro)

    @coroutine
    def start_after(self, coro, delay):
        return (yield SYSCALL_NURSERY_START_AFTER, self, coro, delay)