from types import coroutine
from .._syscalls import SYSCALL_POOL_EXECUTE


@coroutine
def execute(_name, *args, **kwargs):
    return (yield SYSCALL_POOL_EXECUTE, _name, args, kwargs)
