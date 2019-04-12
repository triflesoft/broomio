from .._syscalls import SYSCALL_TASK_SLEEP
from types import coroutine


@coroutine
def sleep(delay):
    yield SYSCALL_TASK_SLEEP, delay
