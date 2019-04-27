from types import coroutine
from .._syscalls import SYSCALL_TASK_SLEEP


@coroutine
def sleep(delay):
    yield SYSCALL_TASK_SLEEP, delay
