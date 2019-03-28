from .._info import SOCKET_KIND_CLIENT_CONNECTION
from .._info import SOCKET_KIND_SERVER_CONNECTION
from .._info import SOCKET_KIND_SERVER_LISTENING
from .._info import SOCKET_KIND_UNKNOWN
from .._sock import socket
from .._util import _get_coro_stack_frames
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


class LoopTaskDeque(object):
    def __init__(self):
        self._info = None

    def _process_task(self):
        # Cycle while there are tasks ready for execution.
        # New tasks may be enqueued while this loop cycles.
        while len(self._info.task_deque) > 0:
            # Get next task.
            task_info = self._info.task_deque.pop()
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

                    # Throw exception
                    task_info.coro.throw(type(task_info.throw_exc), task_info.throw_exc, prev_traceback)
                else:
                    # Execute task.
                    task_info.yield_func, *task_info.yield_args = task_info.coro.send(task_info.send_args)
                    # Clean up send_args. If any syscall was requested, send_args will be assigned accordingly.
                    task_info.send_args = None

                coro_succeeded = True
            except StopIteration:
                # This code is copy-paste of "GeneratorExit" handling, \
                # but it will not be so in future.
                # Task completed successfully.
                # Remove task from nursery.
                nursery = task_info.nursery
                nursery._children.remove(task_info)

                # Was that task the last nursery child?
                if len(nursery._children) == 0:
                    # Notify all watchers.
                    for watcher in nursery._watchers:
                        self._info.task_enqueue_old(watcher)

                del nursery
            except GeneratorExit:
                # This code is copy-paste of "StopIteration" handling, \
                # but it will not be so in future.
                # Task completed because we requested it to complete.
                # Remove task from nursery.
                nursery = task_info.nursery
                nursery._children.remove(task_info)

                # Was that task the last nursery child?
                if len(nursery._children) == 0:
                    # Notify all watchers.
                    for watcher in nursery._watchers:
                        self._info.task_enqueue_old(watcher)

                del nursery
            except Exception:
                # Task failed, exception thrown.
                # Remove child task from nursery.
                nursery = task_info.nursery
                nursery._children.remove(task_info)

                # Was that task the last nursery child?
                if len(nursery._children) == 0:
                    # Notify all watchers.
                    for watcher in nursery._watchers:
                        self._info.task_enqueue_old(watcher)
                else:
                    # Cancel all other child tasks.
                    # Child task is already queued either in task_deque, time_heapq or sock_array.
                    # If child task is already is task_deque there is no need to add it to task_deque again.
                    # However if child task is in time_heapq or sock_array, it must be removed from there \
                    # and aded to task_deque for throwing an exception.
                    has_time_changes = False

                    for child in nursery._children:
                        # Throw exception in task.
                        # TODO: Is this the best exception type to throw inside coroutine to cancel it?
                        child.throw_exc = GeneratorExit(None)

                        if not child.recv_fileno is None:
                            # This task is waiting for socket to become readable.
                            socket_info = self._info.get_sock_info(child.recv_fileno)

                            assert child == socket_info.recv_task_info, 'Internal data structures are damaged.'

                            # Unbind task and socket.
                            child.recv_fileno = None
                            socket_info.recv_task_info = None
                            self._info.socket_task_count -= 1

                            # Note that socket may be registered for writing notification.
                            socket_info.event_mask &= 0x_FFFE # ~0x_0001 EPOLLIN

                            if socket_info.event_mask == 0:
                                self._info.socket_epoll.unregister(child.recv_fileno)
                            else:
                                self._info.socket_epoll.modify(child.recv_fileno, socket_info.event_mask)

                            self._info.socket_wait_count -= 1

                            # Enqueue task.
                            self._info.task_enqueue_old(child)

                            del socket_info
                        elif not child.send_fileno is None:
                            # This task is waiting for socket to become writable.
                            socket_info = self._info.get_sock_info(child.send_fileno)

                            assert child == socket_info.send_task_info, 'Internal data structures are damaged.'

                            # Unbind task and socket.
                            child.send_fileno = None
                            socket_info.send_task_info = None
                            self._info.socket_task_count -= 1

                            # Note that socket may be registered for reading notification.
                            socket_info.event_mask &= 0x_FFFB # ~0x_0004 EPOLLOUT

                            if socket_info.event_mask == 0:
                                self._info.socket_epoll.unregister(child.send_fileno)
                            else:
                                self._info.socket_epoll.modify(child.send_fileno, socket_info.event_mask)

                            self._info.socket_wait_count -= 1

                            # Enqueue task.
                            self._info.task_enqueue_old(child)

                            del socket_info
                        else:
                            try:
                                # If child was scheduled to run later, cancel that \
                                # and reschedule task to be tun in current tick.
                                index = 0

                                while index < len(self._info.time_heapq):
                                    _, time_task_info = self._info.time_heapq[index]

                                    if time_task_info == child:
                                        self._info.time_heapq.pop(index)
                                        has_time_changes = True
                                        self._info.task_enqueue_old(child)
                                        break
                                    else:
                                        index += 1
                            except ValueError:
                                pass

                    # HeapQ must be rebuilt.
                    if has_time_changes:
                        heapify(self._info.time_heapq)

                    del has_time_changes
                del nursery

            if coro_succeeded:
                if task_info.yield_func == SYSCALL_TASK_SLEEP:
                    # Delay task execution.
                    delay = float(task_info.yield_args[0])

                    # Is delay greater than zero?
                    if delay > 0:
                        # Schedule for later execution.
                        heappush(self._info.time_heapq, (self._info.now + delay, task_info))
                    else:
                        # Otherwise enqueue task to be executed in current tick.
                        self._info.task_enqueue_old(task_info)

                    del delay
                elif task_info.yield_func == SYSCALL_NURSERY_JOIN:
                    # Wait for all nursery tasks to be finished.
                    nursery = task_info.yield_args[0]
                    nursery._watchers.add(task_info)

                    del nursery
                elif task_info.yield_func == SYSCALL_NURSERY_KILL:
                    # TODO: SYSCALL_NURSERY_KILL is not implemented yet.
                    # TODO: Cancel all tasks in nursery.
                    nursery, exception_type, exception, traceback = task_info.yield_args

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
                    self._info.task_enqueue_new(coro, task_info, stack_frames, nursery)
                    # Enqueue current (parent) task.
                    self._info.task_enqueue_old(task_info)

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
                        self._info.task_enqueue_new_delay(coro, task_info, stack_frames, nursery, delay)
                    else:
                        # Enqueue child task. Current task will be parent.
                        self._info.task_enqueue_new(coro, task_info, stack_frames, nursery)

                    # Enqueue current (parent) task.
                    self._info.task_enqueue_old(task_info)

                    del stack_frames
                    del delay
                    del coro
                    del nursery
                elif task_info.yield_func in SYSCALL_SOCKET_READ:
                    # Some kind of socket reading.

                    sock = task_info.yield_args[0]
                    fileno = sock.fileno()
                    socket_info = self._info.get_sock_info(fileno)

                    assert socket_info.recv_task_info is None, f'Another task {socket_info.recv_task_info.coro} is already receiving on this socket.'
                    assert task_info.recv_fileno is None, 'Task is already waiting for another socket to become readable.'
                    assert task_info.send_fileno is None, 'Task is already waiting for another socket to become writable.'

                    if socket_info.recv_ready:
                        # Socket is already ready for reading.
                        socket_info.recv_ready = False

                        assert socket_info.recv_task_info is None, 'Internal data structures are damaged.'

                        if task_info.yield_func == SYSCALL_SOCKET_ACCEPT:
                            assert socket_info.kind == SOCKET_KIND_SERVER_LISTENING, 'Internal data structures are damaged.'
                            # Accept as many connections as possible.
                            _, nursery, handler_factory = task_info.yield_args
                            # Extract parent coroutine call chain frames.
                            stack_frames = _get_coro_stack_frames(task_info.coro)

                            try:
                                while True:
                                    client_socket, client_address = sock.accept()
                                    client_socket_info = self._info.sock_array[client_socket.fileno()]
                                    assert client_socket_info.kind == SOCKET_KIND_UNKNOWN, 'Internal data structures are damaged.'
                                    client_socket_info.kind = SOCKET_KIND_SERVER_CONNECTION
                                    handler = handler_factory(socket(sock=client_socket), client_address)
                                    self._info.task_enqueue_new(handler, task_info, stack_frames, nursery)
                            except OSError:
                                pass

                            self._info.task_enqueue_old(task_info)

                            del handler
                            del client_address
                            del client_socket
                            del handler_factory
                            del nursery
                            del sock
                        elif task_info.yield_func == SYSCALL_SOCKET_RECV:
                            # Receive data.
                            sock, size = task_info.yield_args
                            data = sock.recv(size)
                            # Enqueue task.
                            task_info.send_args = data
                            self._info.task_enqueue_old(task_info)

                            del data
                            del size
                            del sock
                        elif task_info.yield_func == SYSCALL_SOCKET_RECV_INTO:
                            # Receive data.
                            sock, data, size = task_info.yield_args
                            size = sock.recv_into(data, size)
                            # Enqueue task.
                            task_info.send_args = size
                            self._info.task_enqueue_old(task_info)

                            del data
                            del size
                            del sock
                        elif task_info.yield_func == SYSCALL_SOCKET_RECVFROM:
                            # Receive data.
                            sock, size = task_info.yield_args
                            data, addr = sock.recvfrom(size)
                            # Enqueue task.
                            task_info.send_args = data, addr
                            self._info.task_enqueue_old(task_info)

                            del addr
                            del data
                            del size
                            del sock
                        elif task_info.yield_func == SYSCALL_SOCKET_RECVFROM_INTO:
                            # Receive data.
                            sock, data, size = task_info.yield_args
                            size, addr = sock.recvfrom_into(data, size)
                            # Enqueue task.
                            task_info.send_args = size, addr
                            self._info.task_enqueue_old(task_info)

                            del addr
                            del size
                            del data
                            del sock
                        else:
                            assert False, f'Unexpected syscall {task_info.yield_func}.'
                    else:
                        # Socket is not yet ready for reading.
                        # Bind task and socket.
                        socket_info.recv_task_info = task_info
                        task_info.recv_fileno = fileno
                        self._info.socket_task_count += 1

                        # Is socket registered for reading notification?
                        if socket_info.event_mask & 0x_0001 == 0: # EPOLLIN
                            # Note that socket may be registered for writing notification.
                            socket_info.event_mask |= 0x_2019 # EPOLLRDHUP | EPOLLHUP | EPOLLERR | EPOLLIN

                            if socket_info.event_mask & 0x_0004 == 0: # EPOLLOUT
                                self._info.socket_epoll.register(fileno, socket_info.event_mask)
                            else:
                                self._info.socket_epoll.modify(fileno, socket_info.event_mask)

                            self._info.socket_wait_count += 1

                    del socket_info
                    del fileno
                    del sock
                elif task_info.yield_func in SYSCALL_SOCKET_WRITE:
                    # Some kind of socket writing.
                    sock = task_info.yield_args[0]
                    fileno = sock.fileno()
                    socket_info = self._info.get_sock_info(fileno)

                    assert socket_info.send_task_info is None, f'Another task {socket_info.send_task_info.coro} is already sending on this socket.'
                    assert task_info.recv_fileno is None, 'Task is already waiting for another socket to become readable.'
                    assert task_info.send_fileno is None, 'Task is already waiting for another socket to become writable.'

                    if socket_info.send_ready:
                        # Socket is already ready for writing.
                        socket_info.send_ready = False

                        assert socket_info.send_task_info is None, 'Internal data structures are damaged.'

                        if task_info.yield_func == SYSCALL_SOCKET_CLOSE:
                            # Close socket.
                            # Is socket registered for reading notification?
                            if socket_info.event_mask & 0x_0001 == 0x_0001: # EPOLLIN
                                self._info.socket_wait_count -= 1

                            # Is socket registered for writing notification?
                            if socket_info.event_mask & 0x_0004 == 0x_0004: # EPOLLOUT
                                self._info.socket_wait_count -= 1

                            self._info.socket_epoll.unregister(fileno)

                            # Close socket and reset socket info.
                            sock.close()
                            socket_info.kind = SOCKET_KIND_UNKNOWN

                            if socket_info.recv_task_info:
                                socket_info.recv_task_info = None
                                self._info.socket_task_count -= 1

                            socket_info.recv_ready = False
                            socket_info.send_ready = False
                            socket_info.event_mask = 0

                            self._info.task_enqueue_old(task_info)
                        elif task_info.yield_func == SYSCALL_SOCKET_SEND:
                            # Send data.
                            sock, data = task_info.yield_args
                            size = sock.send(data)
                            # Enqueue task.
                            task_info.send_args = size
                            self._info.task_enqueue_old(task_info)

                            del data
                            del size
                        elif task_info.yield_func == SYSCALL_SOCKET_SENDTO:
                            # Send data.
                            sock, data, addr = task_info.yield_args
                            size = sock.sendto(data, addr)
                            # Enqueue task.
                            task_info.send_args = size
                            self._info.task_enqueue_old(task_info)

                            del size
                            del addr
                            del data
                            del sock
                        elif task_info.yield_func == SYSCALL_SOCKET_SHUTDOWN:
                            # TODO: SYSCALL_SOCKET_SHUTDOWN is not implemented yet.
                            pass
                        else:
                            assert False, f'Unexpected syscall {task_info.yield_func}.'
                    else:
                        if (task_info.yield_func == SYSCALL_SOCKET_CLOSE) and (socket_info.kind == SOCKET_KIND_SERVER_LISTENING):
                            # Close socket.
                            # Is socket registered for reading notification?
                            if socket_info.event_mask & 0x_0001 == 0x_0001: # EPOLLIN
                                self._info.socket_wait_count -= 1

                            # Is socket registered for writing notification?
                            if socket_info.event_mask & 0x_0004 == 0x_0004: # EPOLLOUT
                                self._info.socket_wait_count -= 1

                            self._info.socket_epoll.unregister(fileno)

                            # Close socket and reset socket info.
                            sock.close()
                            socket_info.kind = SOCKET_KIND_UNKNOWN
                            socket_info.send_task_info = None
                            self._info.socket_task_count -= 1

                            if socket_info.recv_task_info:
                                socket_info.recv_task_info = None
                                self._info.socket_task_count -= 1

                            socket_info.recv_ready = False
                            socket_info.send_ready = False
                            socket_info.event_mask = 0

                            self._info.task_enqueue_old(task_info)
                        else:
                            # Socket is not yet ready for writing.
                            # Bind task and socket.
                            socket_info.send_task_info = task_info
                            task_info.send_fileno = fileno
                            self._info.socket_task_count += 1

                            # Is socket registered for writing notification?
                            if socket_info.event_mask & 0x_0004 == 0: # EPOLLOUT
                                # Note that socket may be registered for reading notification.
                                socket_info.event_mask |= 0x_201C # EPOLLRDHUP | EPOLLHUP | EPOLLERR | EPOLLOUT

                                if socket_info.event_mask & 0x_0001 == 0: # EPOLLIN
                                    self._info.socket_epoll.register(fileno, socket_info.event_mask)
                                else:
                                    self._info.socket_epoll.modify(fileno, socket_info.event_mask)

                                self._info.socket_wait_count += 1

                    del socket_info
                    del fileno
                    del sock
                elif task_info.yield_func == SYSCALL_SOCKET_CONNECT:
                    # Connect.
                    sock, addr = task_info.yield_args
                    fileno = sock.fileno()
                    socket_info = self._info.get_sock_info(fileno)

                    assert socket_info.send_task_info is None, f'Another task {socket_info.send_task_info.coro} is already sending on this socket.'
                    assert task_info.recv_fileno is None, 'Task is already waiting for another socket to become readable.'
                    assert task_info.send_fileno is None, 'Task is already waiting for another socket to become writable.'

                    # Bind task and socket.
                    socket_info.send_task_info = task_info
                    task_info.send_fileno = fileno
                    self._info.socket_task_count += 1

                    # Is socket registered for writing notification?
                    if socket_info.event_mask & 0x_0004 == 0: # EPOLLOUT
                        # Note that socket may be registered for reading notification.
                        socket_info.event_mask |= 0x_201D # EPOLLRDHUP | EPOLLHUP | EPOLLERR | EPOLLIN | EPOLLOUT

                        self._info.socket_epoll.register(fileno, socket_info.event_mask)
                        self._info.socket_wait_count += 2

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
                    socket_info = self._info.get_sock_info(fileno)

                    assert socket_info.send_task_info is None, f'Another task {socket_info.send_task_info.coro} is already sending on this socket.'
                    assert socket_info.recv_task_info is None, f'Another task {socket_info.recv_task_info.coro} is already receiving on this socket.'
                    assert task_info.recv_fileno is None, 'Task is already waiting for another socket to become readable.'
                    assert task_info.send_fileno is None, 'Task is already waiting for another socket to become writable.'

                    sock.listen(backlog)

                    socket_info.kind = SOCKET_KIND_SERVER_LISTENING

                    self._info.task_enqueue_old(task_info)

                    del socket_info
                    del fileno
                    del backlog
                    del sock
                else:
                    assert False, f'Unexpected syscall {task_info.yield_func}.'

        return True
