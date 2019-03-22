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
class _SocketInfo(object):
    __slots__ = \
        'fileno', \
        'recv_task_info', 'send_task_info', \
        'recv_ready', 'send_ready', \
        'event_mask'

    def __init__(self, fileno):
        # Socket descriptor.
        self.fileno = fileno
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


class _SelectFakePoll(object):
    def __init__(self):
        pass

    def register(self, fd, eventmask):
        pass

    def modify(self, fd, eventmask):
        pass

    def unregister(self, fd):
        pass

    def poll(self, timeout):
        pass

#
# Loop intofmation
#
class _LoopInfo(object):
    __slots__ = \
        'task_deque', 'task_enqueue_old', 'task_nursery', \
        'time_heapq', 'now', \
        'sock_array', 'sock_dict', 'get_sock_info', 'socket_recv_count', 'socket_send_count', 'socket_epoll'

    def __init__(self, task_nursery):
        from collections import deque
        from resource import getrlimit
        from resource import RLIMIT_NOFILE

        _, nofile_hard = getrlimit(RLIMIT_NOFILE)

        # Deque with tasks ready to be executed.
        # These are new tasks or tasks for which requested syscall completed.
        self.task_deque = deque()

        # SPEED: Much faster than declaring method, which calls method.
        # SPEED:
        # SPEED: def task_enqueue_old(self, task_info): # THIS IS SLOW
        # SPEED:     self.task_deque.append(task_info)  # THIS IS SLOW
        # SPEED:
        self.task_enqueue_old = self.task_deque.append

        # Root nursery.
        self.task_nursery = task_nursery

        # HeapQ with tasks scheduled to run later.9o
        self.time_heapq = []
        self.now = 0

        # For Linux: \
        # Array of sockets. Indexes in list are file descriptors. O(1) access time.
        # Why can we do this? Man page socket(2) states:
        #     The file descriptor returned by a successful call will be \
        #     the lowest-numbered file descriptor not currently open for the process.
        # While some indexes will not be used, for instance 0, 1, and 2, because \
        # they will correspond to file descriptors opened by different means, we \
        # still may assume values of file descriptors to be small integers.
        # For Windows \
        # Dict of sockets. Keys in dict are file descriptors. O(log(N)) access time.
        # No assumptions about socket file descriptor values' range \
        # can possibly be deducted from MSDN.
        self.sock_array = [_SocketInfo(fileno) for fileno in range(nofile_hard)]

        # SPEED: Much faster than declaring method, which calls method.
        # SPEED:
        # SPEED: def get_sock_info(self, fileno):   # THIS IS SLOW
        # SPEED:     return self.sock_array[fileno] # THIS IS SLOW
        # SPEED:
        self.get_sock_info = self.sock_array.__getitem__

        # Number of sockets waiting to become readable.
        self.socket_recv_count = 0

        # Number of sockets waiting to become writable.
        self.socket_send_count = 0

        # Linux specific for now.
        # TODO: Support poll.
        # TODO: Support select.

        try:
            from select import poll

            self.socket_epoll = poll(1024)
        except ModuleNotFoundError:
            try:
                from select import poll

                self.socket_epoll = poll()
            except ModuleNotFoundError:
                self.socket_epoll = _SelectFakePoll()

    def task_enqueue_new(self, coro, parent_task_info, stack_frames, nursery):
        child_task_info = _TaskInfo(coro, parent_task_info, stack_frames, nursery)
        self.task_deque.append(child_task_info)

