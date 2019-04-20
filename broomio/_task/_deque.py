from . import _TaskInfo
from . import CoroutineTracebackException
from . import NurseryError
from . import NurseryExceptionPolicy
from .._sock import SOCKET_KIND_SERVER_LISTENING
from .._sock import SOCKET_KIND_UNKNOWN
from .._syscalls import SYSCALL_NURSERY_INIT
from .._syscalls import SYSCALL_NURSERY_JOIN
from .._syscalls import SYSCALL_NURSERY_KILL
from .._syscalls import SYSCALL_NURSERY_START_LATER
from .._syscalls import SYSCALL_NURSERY_START_SOON
from .._syscalls import SYSCALL_SOCKET_ACCEPT
from .._syscalls import SYSCALL_SOCKET_CLOSE
from .._syscalls import SYSCALL_SOCKET_CONNECT
from .._syscalls import SYSCALL_SOCKET_LISTEN
from .._syscalls import SYSCALL_SOCKET_RECV
from .._syscalls import SYSCALL_SOCKET_RECV_INTO
from .._syscalls import SYSCALL_SOCKET_RECVFROM
from .._syscalls import SYSCALL_SOCKET_RECVFROM_INTO
from .._syscalls import SYSCALL_SOCKET_SEND
from .._syscalls import SYSCALL_SOCKET_SENDTO
from .._syscalls import SYSCALL_SOCKET_SHUTDOWN
from .._syscalls import SYSCALL_TASK_SLEEP
from .._util import _get_coro_stack_frames
from .._util import _LoopSlots
from heapq import heapify
from heapq import heappush
from types import TracebackType


SYSCALL_SOCKET_READ  = set([
    SYSCALL_SOCKET_ACCEPT,
    SYSCALL_SOCKET_RECV,
    SYSCALL_SOCKET_RECV_INTO,
    SYSCALL_SOCKET_RECVFROM,
    SYSCALL_SOCKET_RECVFROM_INTO])

SYSCALL_SOCKET_WRITE = set([
    SYSCALL_SOCKET_CLOSE,
    SYSCALL_SOCKET_SEND,
    SYSCALL_SOCKET_SENDTO,
    SYSCALL_SOCKET_SHUTDOWN])


class TaskAbortError(BaseException):
    pass


class LoopTaskDeque(_LoopSlots):
    def _nursery_abort_children(self, nursery):
        # Child task is already queued either in _task_deque, _time_heapq or _sock_array.
        # If child task is already is _task_deque there is no need to add it to _task_deque again.
        # However if child task is in _time_heapq or _sock_array, it must be removed from there \
        # and added to _task_deque for throwing an exception.
        has_time_changes = False

        for child_task_info in nursery._children:
            if child_task_info.child_nursery:
                self._nursery_abort_children(child_task_info.child_nursery)

            has_time_changes = has_time_changes or (self._task_abort(child_task_info) == 'time')

        # HeapQ must be rebuilt.
        if has_time_changes:
            heapify(self._time_heapq)

    def _nursery_process_exception(self, nursery, task_info, exception):
        if nursery._exception_policy == NurseryExceptionPolicy.Abort:
            # Save exception
            nursery._exceptions.append((task_info, exception))
            # Cancel all child tasks.
            self._nursery_abort_children(nursery)
        elif nursery._exception_policy == NurseryExceptionPolicy.Accumulate:
            # Save exception
            nursery._exceptions.append((task_info, exception))
        elif nursery._exception_policy == NurseryExceptionPolicy.Ignore:
            pass
        else:
            assert False, f'Unexpected nursery exception policy {nursery._exception_policy}.'

    def _nursery_notify_watchers(self, nursery):
        # Was that task the last nursery child?
        if len(nursery._children) == 0:
            # Notify all watchers.
            for watcher_task_info in nursery._watchers:
                if nursery._exceptions:
                    watcher_task_info.throw_exc = NurseryError(nursery._exceptions)
                    watcher_task_info.throw_exc.__cause__ = nursery._exceptions[0][1]

                possible_owner_task_info = watcher_task_info

                # FIXME: Validate algorithm.
                # Looks like passing Nursery between siblings is not supported at all.
                while possible_owner_task_info:
                    if possible_owner_task_info.child_nursery == nursery:
                        possible_owner_task_info.child_nursery = None
                        break

                    possible_owner_task_info = possible_owner_task_info.parent_task_info

                self._task_enqueue_old(watcher_task_info)

    def _task_abort(self, task_info):
        # Throw exception in task.
        task_info.throw_exc = TaskAbortError()

        if not task_info.recv_fileno is None:
            # This task is waiting for socket to become readable.
            socket_info = self._get_sock_info(task_info.recv_fileno)

            assert task_info == socket_info.recv_task_info, f'Internal data structures are damaged for socket #{socket_info.fileno} ({socket_info.kind}).'

            # Unbind task and socket.
            task_info.recv_fileno = None
            socket_info.recv_task_info = None
            self._socket_task_count -= 1
            self._epoll_unregister(socket_info, 0x_0001) # EPOLLIN

            # Enqueue task.
            self._task_enqueue_old(task_info)

            return 'sock/recv'

        if not task_info.send_fileno is None:
            # This task is waiting for socket to become writable.
            socket_info = self._get_sock_info(task_info.send_fileno)

            assert task_info == socket_info.send_task_info, f'Internal data structures are damaged for socket #{socket_info.fileno} ({socket_info.kind}).'

            # Unbind task and socket.
            task_info.send_fileno = None
            socket_info.send_task_info = None
            self._socket_task_count -= 1
            self._epoll_unregister(socket_info, 0x_0004) # EPOLLOUT

            # Enqueue task.
            self._task_enqueue_old(task_info)

            return 'sock/send'
        
        try:
            # If child was scheduled to run later, cancel that \
            # and reschedule task to be run in current tick.
            index = 0

            while index < len(self._time_heapq):
                _, operation, time_task_info = self._time_heapq[index]

                if (operation == 0x_01) and (time_task_info == task_info):
                    self._time_heapq.pop(index)
                    self._task_enqueue_old(task_info)

                    return 'time'
                index += 1
        except ValueError:
            pass

    def _task_enqueue_new(self, coro, parent_task_info, stack_frames, parent_nursery):
        child_task_info = _TaskInfo(coro, parent_task_info, stack_frames, parent_nursery)
        parent_nursery._children.add(child_task_info)
        self._task_enqueue_old(child_task_info)

    def _task_enqueue_new_delay(self, coro, parent_task_info, stack_frames, parent_nursery, delay):
        child_task_info = _TaskInfo(coro, parent_task_info, stack_frames, parent_nursery)
        parent_nursery._children.add(child_task_info)
        heappush(self._time_heapq, (self._now + delay, 0x_01, child_task_info))

    def _process_task(self):
        # Cycle while there are tasks ready for execution.
        # New tasks may be enqueued while this loop cycles.
        while len(self._task_deque) > 0:
            # Get next task.
            task_info = self._task_deque.pop()
            coro_succeeded = False

            try:
                # Should we throw an exception?
                if not task_info.throw_exc is None:
                    # Go through parent task linked list and build call chain
                    frame_task_infos = []
                    frame_task_info = task_info

                    while not frame_task_info is None:
                        frame_task_infos.append(frame_task_info)
                        frame_task_info = frame_task_info.parent_task_info

                    frame_task_infos = reversed(frame_task_infos)

                    # Create beautiful traceback object
                    prev_traceback = None

                    for frame_task_info in frame_task_infos:
                        for stack_frame in frame_task_info.stack_frames:
                            prev_traceback = TracebackType(prev_traceback, stack_frame, stack_frame.f_lasti, stack_frame.f_lineno)

                    # Fake traceback is provided as __cause__, because otherwise, if provided as third argument of
                    # coro.throw, then fake parent coroutine state is corrupted.
                    task_info.throw_exc.__cause__ = CoroutineTracebackException().with_traceback(prev_traceback)

                    try:
                        # Throw exception
                        # Fake traceback is provided as __cause__, because otherwise, if provided as third argument of
                        # coro.throw, then fake parent coroutine state is corrupted.
                        # task_info.yield_func, *task_info.yield_args = task_info.coro.throw(type(task_info.throw_exc), task_info.throw_exc, prev_traceback) # THIS CAUSES PROB
                        task_info.yield_func, *task_info.yield_args = task_info.coro.throw(type(task_info.throw_exc), task_info.throw_exc)
                    finally:
                        # Clean up throw_exc. If any exception will be thrown, throw_exc will be assigned accordingly.
                        task_info.throw_exc = None
                else:
                    try:
                        # Execute task.
                        task_info.yield_func, *task_info.yield_args = task_info.coro.send(task_info.send_args)
                    finally:
                        # Clean up send_args. If any syscall was requested, send_args will be assigned accordingly.
                        task_info.send_args = None

                coro_succeeded = True
            except StopIteration:
                # This code is copy-paste of "GeneratorExit" handling, \
                # but it will not be so in future.
                # Task completed successfully.
                # Remove task from parent_nursery.
                parent_nursery = task_info.parent_nursery
                parent_nursery._children.remove(task_info)
                # Notify watchers
                self._nursery_notify_watchers(parent_nursery)

                del parent_nursery
            except TaskAbortError:
                # This code is copy-paste of "StopIteration" handling, \
                # but it will not be so in future.
                # Task completed because we requested it to complete.
                # Remove task from parent_nursery.
                parent_nursery = task_info.parent_nursery
                parent_nursery._children.remove(task_info)
                # Notify watchers
                self._nursery_notify_watchers(parent_nursery)

                del parent_nursery
            except Exception as child_exception:
                # Task failed, exception thrown.
                # Remove child task from parent_nursery.
                parent_nursery = task_info.parent_nursery
                parent_nursery._children.remove(task_info)

                # Process exception
                self._nursery_process_exception(parent_nursery, task_info, child_exception)
                # Notify watchers
                self._nursery_notify_watchers(parent_nursery)

                del parent_nursery

            if coro_succeeded:
                if task_info.yield_func == SYSCALL_TASK_SLEEP:
                    # Delay task execution.
                    delay = float(task_info.yield_args[0])

                    # Is delay greater than zero?
                    if delay > 0:
                        # Schedule for later execution.
                        heappush(self._time_heapq, (self._now + delay, 0x_01, task_info))
                    else:
                        # Otherwise enqueue task to be executed in current tick.
                        self._task_enqueue_old(task_info)

                    del delay
                elif task_info.yield_func == SYSCALL_NURSERY_INIT:
                    # Wait for all nursery tasks to be finished.
                    nursery = task_info.yield_args[0]
                    nursery._task_info = task_info
                    task_info.child_nursery = nursery
                    task_info.send_args = nursery
                    self._task_enqueue_old(task_info)

                    if nursery._timeout > 0:
                        heappush(self._time_heapq, (self._now + nursery._timeout, 0x_02, nursery))
                        heappush(self._time_heapq, (self._now + nursery._timeout, 0x_02, task_info))

                    del nursery
                elif task_info.yield_func == SYSCALL_NURSERY_JOIN:
                    # Wait for all nursery tasks to be finished.
                    nursery = task_info.yield_args[0]

                    if len(nursery._children) > 0:
                        nursery._watchers.add(task_info)
                    else:
                        self._task_enqueue_old(task_info)

                    del nursery
                elif task_info.yield_func == SYSCALL_NURSERY_KILL:
                    # Cancel all nursery tasks.
                    nursery, exception_type, exception, traceback = task_info.yield_args
                    # Process exception
                    self._nursery_process_exception(nursery, task_info, exception)
                    # Notify watchers
                    self._nursery_notify_watchers(nursery)

                    # Enqueue task to be executed in current tick.
                    task_info.throw_exc = exception
                    self._task_enqueue_old(task_info)

                    del nursery
                    del exception_type
                    del exception
                    del traceback
                elif task_info.yield_func == SYSCALL_NURSERY_START_SOON:
                    # Enqueue task for execution in current tick.
                    nursery, coro = task_info.yield_args
                    # Extract parent coroutine call chain frames.
                    stack_frames = _get_coro_stack_frames(task_info.coro)
                    # Enqueue child task. Current task will be parent.
                    self._task_enqueue_new(coro, task_info, stack_frames, nursery)
                    # Enqueue current (parent) task.
                    self._task_enqueue_old(task_info)

                    del coro
                    del nursery
                elif task_info.yield_func == SYSCALL_NURSERY_START_LATER:
                    # Enqueue task for execution after delay.
                    nursery, coro, delay = task_info.yield_args
                    delay = float(delay)
                    # Extract parent coroutine call chain frames.
                    stack_frames = _get_coro_stack_frames(task_info.coro)

                    # Is delay greater than zero?
                    if delay > 0:
                        # Enqueue child task. Current task will be parent.
                        self._task_enqueue_new_delay(coro, task_info, stack_frames, nursery, delay)
                    else:
                        # Enqueue child task. Current task will be parent.
                        self._task_enqueue_new(coro, task_info, stack_frames, nursery)

                    # Enqueue current (parent) task.
                    self._task_enqueue_old(task_info)

                    del stack_frames
                    del delay
                    del coro
                    del nursery
                elif task_info.yield_func in SYSCALL_SOCKET_READ:
                    # Some kind of socket reading.

                    sock = task_info.yield_args[0]
                    fileno = sock.fileno()
                    socket_info = self._get_sock_info(fileno)

                    assert socket_info.recv_task_info is None, f'Another task {socket_info.recv_task_info.coro} is already receiving on this socket.'
                    assert task_info.recv_fileno is None, 'Task is already waiting for another socket to become readable.'
                    assert task_info.send_fileno is None, 'Task is already waiting for another socket to become writable.'

                    if socket_info.recv_ready:
                        # Socket is already ready for reading.
                        socket_info.recv_ready = False

                        assert socket_info.recv_task_info is None, f'Internal data structures are damaged for socket #{socket_info.fileno} ({socket_info.kind}).'

                        if task_info.yield_func == SYSCALL_SOCKET_ACCEPT:
                            self._sock_accept(task_info, socket_info)
                        elif task_info.yield_func == SYSCALL_SOCKET_RECV:
                            self._sock_recv(task_info, socket_info)
                        elif task_info.yield_func == SYSCALL_SOCKET_RECV_INTO:
                            self._sock_recv_into(task_info, socket_info)
                        elif task_info.yield_func == SYSCALL_SOCKET_RECVFROM:
                            self._sock_recvfrom(task_info, socket_info)
                        elif task_info.yield_func == SYSCALL_SOCKET_RECVFROM_INTO:
                            self._sock_recvfrom_into(task_info, socket_info)
                        else:
                            assert False, f'Unexpected syscall {task_info.yield_func}.'
                    else:
                        # Socket is not yet ready for reading.
                        # Bind task and socket.
                        socket_info.recv_task_info = task_info
                        self._socket_task_count += 1
                        task_info.recv_fileno = fileno
                        self._epoll_register(socket_info, 0x_0001) # EPOLLIN

                    del socket_info
                    del fileno
                    del sock
                elif task_info.yield_func in SYSCALL_SOCKET_WRITE:
                    # Some kind of socket writing.
                    sock = task_info.yield_args[0]
                    fileno = sock.fileno()
                    socket_info = self._get_sock_info(fileno)

                    assert socket_info.send_task_info is None, f'Another task {socket_info.send_task_info.coro} is already sending on this socket.'
                    assert task_info.recv_fileno is None, 'Task is already waiting for another socket to become readable.'
                    assert task_info.send_fileno is None, 'Task is already waiting for another socket to become writable.'

                    if socket_info.send_ready:
                        # Socket is already ready for writing.
                        socket_info.send_ready = False

                        assert socket_info.send_task_info is None, f'Internal data structures are damaged for socket #{socket_info.fileno} ({socket_info.kind}).'

                        if task_info.yield_func == SYSCALL_SOCKET_CLOSE:
                            # Close socket.
                            self._epoll_unregister(socket_info, 0x_0005) # EPOLLIN | EPOLLOUT

                            if socket_info.recv_task_info:
                                socket_info.recv_task_info.recv_fileno = None
                                socket_info.recv_task_info = None
                                self._socket_task_count -= 1

                            self._sock_close(task_info, socket_info)
                        elif task_info.yield_func == SYSCALL_SOCKET_SEND:
                            self._sock_send(task_info, socket_info)
                        elif task_info.yield_func == SYSCALL_SOCKET_SENDTO:
                            self._sock_sendto(task_info, socket_info)
                        elif task_info.yield_func == SYSCALL_SOCKET_SHUTDOWN:
                            self._sock_shutdown(task_info, socket_info)
                        else:
                            assert False, f'Unexpected syscall {task_info.yield_func}.'
                    else:
                        if (task_info.yield_func == SYSCALL_SOCKET_CLOSE) and \
                            ((socket_info.kind == SOCKET_KIND_UNKNOWN) or (socket_info.kind == SOCKET_KIND_SERVER_LISTENING)):
                            # Close socket.
                            socket_info.send_task_info = None
                            self._socket_task_count -= 1
                            self._epoll_unregister(socket_info, 0x_0005) # EPOLLIN | EPOLLOUT

                            if socket_info.recv_task_info:
                                socket_info.recv_task_info.recv_fileno = None
                                socket_info.recv_task_info = None
                                self._socket_task_count -= 1

                            self._sock_close(task_info, socket_info)
                        else:
                            # Socket is not yet ready for writing.
                            # Bind task and socket.
                            socket_info.send_task_info = task_info
                            self._socket_task_count += 1
                            task_info.send_fileno = fileno
                            self._epoll_register(socket_info, 0x_0004) # EPOLLOUT

                    del socket_info
                    del fileno
                    del sock
                elif task_info.yield_func == SYSCALL_SOCKET_CONNECT:
                    # Connect.
                    sock, addr = task_info.yield_args
                    fileno = sock.fileno()
                    socket_info = self._get_sock_info(fileno)

                    assert socket_info.send_task_info is None, f'Another task {socket_info.send_task_info.coro} is already sending on this socket.'
                    assert task_info.recv_fileno is None, 'Task is already waiting for another socket to become readable.'
                    assert task_info.send_fileno is None, 'Task is already waiting for another socket to become writable.'

                    # Bind task and socket.
                    socket_info.send_task_info = task_info
                    self._socket_task_count += 1
                    task_info.send_fileno = fileno
                    self._epoll_register(socket_info, 0x_0005) # EPOLLIN | EPOLLOUT

                    try:
                        sock.connect(addr)
                    except BlockingIOError:
                        pass

                    del socket_info
                    del fileno
                    del addr
                    del sock
                elif task_info.yield_func == SYSCALL_SOCKET_LISTEN:
                    # Listen.
                    sock, backlog = task_info.yield_args
                    fileno = sock.fileno()
                    socket_info = self._get_sock_info(fileno)

                    assert socket_info.send_task_info is None, f'Another task {socket_info.send_task_info.coro} is already sending on this socket.'
                    assert socket_info.recv_task_info is None, f'Another task {socket_info.recv_task_info.coro} is already receiving on this socket.'
                    assert task_info.recv_fileno is None, 'Task is already waiting for another socket to become readable.'
                    assert task_info.send_fileno is None, 'Task is already waiting for another socket to become writable.'

                    sock.listen(backlog)
                    socket_info.kind = SOCKET_KIND_SERVER_LISTENING
                    self._task_enqueue_old(task_info)

                    del socket_info
                    del fileno
                    del backlog
                    del sock
                else:
                    assert False, f'Unexpected syscall {task_info.yield_func}.'

        return True
