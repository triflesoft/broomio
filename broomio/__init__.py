# Fast async I/O module with many tradeoffs.
# Code is fast and thus often intentionally ugly and borderline unmaintanable.
# Beauty of any kind is not priority for this project.
#
# Specific optimizations:
# 1. Data classes use __slots__
# 2. All validations are implented with "assert" statement, thus can be easily
#    disabled in production with "-O" command line switch.
# 3. Entire loop is implemented in one method which accesses only local
#    method variables, no instance attributes or anything like that.
# 4. Named constants are replaced with their values. To make code more readable
#    this values are written as hexadecimal with "0x_" prefix.


# EPOLLIN / POLLIN
# 0x_0001
# The associated file is available for read(2) operations.

# EPOOLPRI / POLLPRI
# 0x_0002
# TODO: Process EPOOLPRI event.
# There is some exceptional condition on the file descriptor.
# Possibilities include:
#     *  There is out-of-band data on a TCP socket (see tcp(7)).
#     *  A pseudoterminal master in packet mode has seen a state
#        change on the slave (see ioctl_tty(2)).
#     *  A cgroup.events file has been modified (see cgroups(7)).

# EPOLLOUT / POLLOUT
# 0x_0004
# The associated file is available for write(2) operations.

# EPOLLERR / POLLERR
# 0x_0008
# TODO: Process POLLERR event.
# Error condition happened on the associated file descriptor.
# This event is also reported for the write end of a pipe when
# the read end has been closed.  epoll_wait(2) will always
# report for this event; it is not necessary to set it in
# events.

# EPOLLHUP / POLLHUP
# 0x_0010
# TODO: Process POLLHUP event.
# Hang up happened on the associated file descriptor.
# epoll_wait(2) will always wait for this event; it is not nec‐
# essary to set it in events.
# Note that when reading from a channel such as a pipe or a
# stream socket, this event merely indicates that the peer
# closed its end of the channel. Subsequent reads from the
# channel will return 0 (end of file) only after all outstanding
# data in the channel has been consumed.

# EPOLLRDHUP / POLLRDHUP
# 0x_2000
# TODO: Process POLLRDHUP event.
# Stream socket peer closed connection, or shut down writing
# half of connection.  (This flag is especially useful for writ‐
# ing simple code to detect peer shutdown when using Edge Trig‐
# gered monitoring.)


# EPOLLRDNORM / POLLRDNORM
# 0x_0040

# EPOLLRDBAND / POLLRDBAND
# 0x_0080

# EPOLLWRNORM / POLLWRNORM
# 0x_0100

# EPOLLWRBAND / POLLWRBAND
# 0x_0200

# EPOLLMSG / POLLMSG
# 0x_0400

from collections import deque
from heapq import heapify
from heapq import heappop
from heapq import heappush
from select import epoll
from socket import AF_INET
from socket import AF_INET6
from socket import error
from socket import IPPROTO_TCP
from socket import IPPROTO_UDP
from socket import SO_REUSEADDR
from socket import SO_REUSEPORT
from socket import SOCK_DGRAM
from socket import SOCK_STREAM
from socket import SOL_SOCKET
from time import sleep as time_sleep
from time import time
from types import coroutine
from traceback import print_exc
from resource import getrlimit
from resource import RLIMIT_NOFILE

#
# SysCalls
#

SYSCALL_TASK_SLEEP           = 0x_01 # Sleep for specified in seconds delay.
SYSCALL_NURSERY_JOIN         = 0x_11 # Wait for all tasks in nursery to complete.
SYSCALL_NURSERY_KILL         = 0x_12 # Kill all tasks in nursery.
SYSCALL_NURSERY_START_SOON   = 0x_13 # Start task in nursery in current tick.
SYSCALL_NURSERY_START_AFTER  = 0x_14 # Start task in nursery after specified in seconds delay.
SYSCALL_SOCKET_ACCEPT        = 0x_51 # Accept as many connections as possible.
SYSCALL_SOCKET_CLOSE         = 0x_52 # Close socket canceling all tasks waiting for the socket.
SYSCALL_SOCKET_CONNECT       = 0x_53 # Connect to IP endpoint.
SYSCALL_SOCKET_RECV          = 0x_54 # Receive data.
SYSCALL_SOCKET_RECV_INTO     = 0x_55 # Receive data.
SYSCALL_SOCKET_RECVFROM      = 0x_56 # Receive data.
SYSCALL_SOCKET_RECVFROM_INTO = 0x_57 # Receive data.
SYSCALL_SOCKET_SEND          = 0x_58 # Send data.
SYSCALL_SOCKET_SENDTO        = 0x_59 # Send data.
SYSCALL_SOCKET_SHUTDOWN      = 0x_5A # Shutdown socket.

SYSCALL_SOCKET_READ  = set([
    SYSCALL_SOCKET_ACCEPT,
    SYSCALL_SOCKET_RECV,
    SYSCALL_SOCKET_RECV_INTO,
    SYSCALL_SOCKET_RECVFROM,
    SYSCALL_SOCKET_RECVFROM_INTO])

SYSCALL_SOCKET_WRITE = set([
    SYSCALL_SOCKET_CLOSE,
    SYSCALL_SOCKET_CONNECT,
    SYSCALL_SOCKET_SEND,
    SYSCALL_SOCKET_SENDTO,
    SYSCALL_SOCKET_SHUTDOWN])


#
# Task information.
#
class _TaskInfo(object):
    __slots__ = 'coro', 'yield_func', 'yield_args', 'send_args', 'throw_args', 'parent_task_info', 'recv_fileno', 'send_fileno', 'nursery'

    def __init__(self, coro, parent_task_info, nursery):
        # Coroutine to be executed.
        self.coro = coro
        # Syscall function coroutine requested.
        self.yield_func = None
        # Syscall arguments coroutine requested.
        self.yield_args = None
        # Result of last syscall to be passed to coroutine.
        self.send_args = None
        # Exception to be passed to coroutine.
        self.throw_args = None
        # Parent task, the one from which nursery.start_soon nursery.start_after was called.
        self.parent_task_info = parent_task_info
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
    __slots__ = 'fileno', 'recv_task_info', 'send_task_info', 'recv_ready', 'send_ready', 'event_mask'

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


#
# Event Loop.
#
class Loop(object):
    def __init__(self):
        # Root nursery.
        self._task_nursery = Nursery()
        # Deque with tasks ready to be executed.
        # These are new tasks or tasks for which requested syscall completed.
        self._task_deque = deque()
        # HeapQ with tasks scheduled to run later.
        self._time_heapq = []

        # Get maximum number of opened files (which includes sockets and pipes).
        _, nofile_hard = getrlimit(RLIMIT_NOFILE)

        # For Linux: \
        # Array of sockets. Indexes in list are file descriptors. O(1) access time.
        # Why can we do this? Man page socket(2) states:
        #     The file descriptor returned by a successful call will be \
        #     the lowest-numbered file descriptor not currently open for the process.
        # While some indexes will not be used, for instance 0, 1, and 2, because \
        # they will correspond to file descriptors opened by different means, we \
        # still may assume values of file descriptors to be small integers.
        self._sock_array = [_SocketInfo(fileno) for fileno in range(nofile_hard)]
        # For Windows \
        # Dict of sockets. Keys in dict are file descriptors. O(log(N)) access time.
        # No assumptions about socket file descriptor values' range \
        # can possibly be deducted from MSDN.
        self._sock_dict = {}

    def start_soon(self, coro):
        # Create task info for root task. Root tasks have no parent.
        # Root tasks can be created after loop was started from \
        # another thread, but that does not look like great idea.
        task_info = _TaskInfo(coro, None, self._task_nursery)
        # Don't forget to add task to root nursery.
        self._task_nursery._children.add(task_info)
        # And also enqueue task.
        self._task_deque.append(task_info)

    def run(self):
        # True if there are any tasks scheduled.
        running = True
        # Copy class members into local variables for faster access.
        task_deque = self._task_deque
        time_heapq = self._time_heapq
        sock_array = self._sock_array
        # Number of sockets waiting to become readable.
        socket_recv_count = 0
        # Number of sockets waiting to become writable.
        socket_send_count = 0
        # Epoll handle.
        socket_epoll = epoll(1024)

        while running:
            # Each loop iteration is a tick.
            try:
                # Current time as reference for timers.
                now = time()

                # Are there tasks ready for execution?
                if len(self._task_deque) > 0:

                    # Cycle while there are tasks ready for execution.
                    # New tasks may be enqueued while this loop cycles.
                    while len(self._task_deque) > 0:
                        # Get next task.
                        task_info = task_deque.pop()

                        try:
                            # Should we throw an exception?
                            if not task_info.throw_args is None:
                                task_info.coro.throw(*task_info.throw_args)
                            else:
                                # Execute task.
                                task_info.yield_func, *task_info.yield_args = task_info.coro.send(task_info.send_args)
                                # Clean up send_args. If any syscall was requested, send_args will be assigned accordingly.
                                task_info.send_args = None

                                if task_info.yield_func == SYSCALL_TASK_SLEEP:
                                    # Delay task execution.
                                    delay = float(task_info.yield_args[0])

                                    # Is delay greater than zero?
                                    if delay > 0:
                                        # Schedule for later execution.
                                        heappush(time_heapq, (now + delay, task_info))
                                    else:
                                        # Otherwise enqueue task to be executed in current tick.
                                        task_deque.append(task_info)

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
                                    # Create task info for a new child task. Current task will be parent.
                                    child_task_info = _TaskInfo(coro, task_info, nursery)
                                    # Don't forget to add task to nursery.
                                    nursery._children.add(child_task_info)
                                    # Enqueue current (parent) task.
                                    task_deque.append(task_info)
                                    # Enqueue child task.
                                    task_deque.append(child_task_info)

                                    del child_task_info
                                    del coro
                                    del nursery
                                elif task_info.yield_func == SYSCALL_NURSERY_START_AFTER:
                                    # Enqueue task for execution after delay.
                                    nursery, coro, delay = task_info.yield_args
                                    delay = float(delay)
                                    # Create task info for a new child task. Current task will be parent.
                                    child_task_info = _TaskInfo(coro, task_info, nursery)
                                    # Don't forget to add task to nursery.
                                    nursery._children.add(child_task_info)
                                    # Enqueue current (parent) task.
                                    task_deque.append(task_info)

                                    # Is delay greater than zero?
                                    if delay > 0:
                                        # Schedule for later execution.
                                        heappush(time_heapq, (now + delay, child_task_info))
                                    else:
                                        # Otherwise enqueue child task to be executed in current tick.
                                        task_deque.append(child_task_info)

                                    del child_task_info
                                    del delay
                                    del coro
                                    del nursery
                                elif task_info.yield_func in SYSCALL_SOCKET_READ:
                                    # Some kind of socket reading.

                                    sock = task_info.yield_args[0]
                                    fileno = sock.fileno()
                                    socket_info = sock_array[fileno]

                                    assert socket_info.recv_task_info is None, f'Another task {socket_info.recv_task_info.coro} is already receiving on this socket.'
                                    assert task_info.recv_fileno is None, 'Task is already waiting for another socket to become readable.'
                                    assert task_info.send_fileno is None, 'Task is already waiting for another socket to become writable.'

                                    if socket_info.recv_ready:
                                        # Socket is already ready for reading.
                                        socket_info.recv_ready = False

                                        assert socket_info.recv_task_info is None, 'Internal data structures are damaged.'

                                        if task_info.yield_func == SYSCALL_SOCKET_ACCEPT:
                                            # Accept as many connections as possible.
                                            _, nursery, handler_factory = task_info.yield_args

                                            try:
                                                while True:
                                                    client_socket, client_address = sock.accept()
                                                    handler = handler_factory(socket(sock=client_socket), client_address)
                                                    handler_task_info = _TaskInfo(handler, task_info, nursery)
                                                    task_deque.append(handler_task_info)
                                            except error:
                                                pass

                                            task_deque.append(task_info)

                                            del handler_task_info
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
                                            task_deque.append(task_info)

                                            del data
                                            del size
                                            del sock
                                        elif task_info.yield_func == SYSCALL_SOCKET_RECV_INTO:
                                            # Receive data.
                                            sock, data, size = task_info.yield_args
                                            size = sock.recv_into(data, size)
                                            # Enqueue task.
                                            task_info.send_args = size
                                            task_deque.append(task_info)

                                            del data
                                            del size
                                            del sock
                                        elif task_info.yield_func == SYSCALL_SOCKET_RECVFROM:
                                            # Receive data.
                                            sock, size = task_info.yield_args
                                            data, addr = sock.recvfrom(size)
                                            # Enqueue task.
                                            task_info.send_args = data, addr
                                            task_deque.append(task_info)

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
                                            task_deque.append(task_info)

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

                                        # Is socket registered for reading notification?
                                        if socket_info.event_mask & 0x_0001 == 0:
                                            # Note that socket may be registered for writing notification.
                                            socket_info.event_mask |= 0x_0001

                                            if socket_info.event_mask == 0x_0001:
                                                socket_epoll.register(fileno, socket_info.event_mask)
                                            else:
                                                socket_epoll.modify(fileno, socket_info.event_mask)

                                            socket_recv_count += 1

                                    del socket_info
                                    del fileno
                                    del sock
                                elif task_info.yield_func in SYSCALL_SOCKET_WRITE:
                                    # Some kind of socket writing.
                                    sock = task_info.yield_args[0]
                                    fileno = sock.fileno()
                                    socket_info = sock_array[fileno]

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
                                            if socket_info.event_mask & 0x_0001 == 0x_0001:
                                                socket_recv_count -= 1

                                            # Is socket registered for writing notification?
                                            if socket_info.event_mask & 0x_0004 == 0x_0004:
                                                socket_send_count -= 1

                                            socket_epoll.unregister(fileno)

                                            # Close socket and reset socket info.
                                            sock.close()
                                            socket_info.recv_task_info = None
                                            socket_info.recv_ready = False
                                            socket_info.send_ready = False
                                            socket_info.event_mask = 0
                                        elif task_info.yield_func == SYSCALL_SOCKET_CONNECT:
                                            # TODO: SYSCALL_SOCKET_CONNECT is not implemented yet.
                                            pass
                                        elif task_info.yield_func == SYSCALL_SOCKET_SEND:
                                            # Send data.
                                            sock, data = task_info.yield_args
                                            size = sock.send(data)
                                            # Enqueue task.
                                            task_info.send_args = size
                                            task_deque.append(task_info)

                                            del data
                                            del size
                                        elif task_info.yield_func == SYSCALL_SOCKET_SENDTO:
                                            # Send data.
                                            sock, data, addr = task_info.yield_args
                                            size = sock.sendto(data, addr)
                                            # Enqueue task.
                                            task_info.send_args = size
                                            task_deque.append(task_info)

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
                                        # Socket is not yet ready for writing.
                                        # Bind task and socket.
                                        socket_info.send_task_info = task_info
                                        task_info.send_fileno = fileno

                                        # Is socket registered for writing notification?
                                        if socket_info.event_mask & 0x_0004 == 0:
                                            # Note that socket may be registered for reading notification.
                                            socket_info.event_mask |= 0x_0004

                                            if socket_info.event_mask == 0x_0004:
                                                socket_epoll.register(fileno, socket_info.event_mask)
                                            else:
                                                socket_epoll.modify(fileno, socket_info.event_mask)

                                            socket_send_count += 1

                                    del socket_info
                                    del fileno
                                    del sock
                                else:
                                    assert False, f'Unexpected syscall {task_info.yield_func}.'
                        except StopIteration:
                            # Task completed successfully.
                            # Remove task from nursery.
                            nursery = task_info.nursery
                            nursery._children.remove(task_info)

                            # Was that task the last nursery child?
                            if len(nursery._children) == 0:
                                # Notify all watchers.
                                for watcher in nursery._watchers:
                                    task_deque.append(watcher)

                            del nursery
                        except GeneratorExit as e:
                            print(e)
                        except Exception as e:
                            # Task failed, exception thrown.
                            # Remove child task from nursery.
                            nursery = task_info.nursery
                            nursery._children.remove(task_info)

                            # Was that task the last nursery child?
                            if len(nursery._children) == 0:
                                # Notify all watchers.
                                for watcher in nursery._watchers:
                                    task_deque.append(watcher)
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
                                    child.throw_args = (GeneratorExit(None), )

                                    if not child.recv_fileno is None:
                                        # This task is waiting for socket to become readable.
                                        socket_info = sock_array[child.recv_fileno]

                                        assert child == socket_info.recv_task_info, 'Internal data structures are damaged.'

                                        # Unbind task and socket.
                                        child.recv_fileno = None
                                        socket_info.recv_task_info = None

                                        # Note that socket may be registered for writing notification.
                                        socket_info.event_mask &= 0x_FFFE # ~0x_0001

                                        if socket_info.event_mask == 0:
                                            socket_epoll.unregister(child.recv_fileno)
                                        else:
                                            socket_epoll.modify(child.recv_fileno, socket_info.event_mask)

                                        socket_recv_count -= 1

                                        # Enqueue task.
                                        task_deque.append(child)

                                        del socket_info
                                    elif not child.send_fileno is None:
                                        # This task is waiting for socket to become writable.
                                        socket_info = sock_array[fileno]

                                        assert child == socket_info.send_task_info, 'Internal data structures are damaged.'

                                        # Unbind task and socket.
                                        child.send_fileno = None
                                        socket_info.send_task_info = None

                                        # Note that socket may be registered for reading notification.
                                        socket_info.event_mask &= 0x_FFFB # ~0x_0004

                                        if socket_info.event_mask == 0:
                                            socket_epoll.unregister(child.send_fileno)
                                        else:
                                            socket_epoll.modify(child.send_fileno, socket_info.event_mask)

                                        socket_send_count -= 1

                                        # Enqueue task.
                                        task_deque.append(child)

                                        del socket_info
                                    else:
                                        try:
                                            # If child was scheduled to run later, cancel that \
                                            # and reschedule task to be tun in current tick.
                                            index = 0

                                            while index < len(time_heapq):
                                                _, time_task_info = time_heapq[index]

                                                if time_task_info == child:
                                                    time_heapq.pop(index)
                                                    has_time_changes = True
                                                    task_deque.append(child)
                                                    break
                                                else:
                                                    index += 1
                                        except ValueError:
                                            pass

                                # HeapQ must be rebuilt.
                                if has_time_changes:
                                    heapify(time_heapq)

                            del has_time_changes
                            del nursery
                # Are there sockets to check for readiness?
                elif socket_recv_count + socket_send_count > 0:
                    # If any tasks are scheduled to be run later, do not make them late.
                    # Otherwise wait for 5 second.
                    # TODO: Justify timeout value, currently 5 seconds.
                    timeout = time_heapq[0][0] - now if len(time_heapq) > 0 else 5
                    events = socket_epoll.poll(timeout)

                    for fileno, event in events:
                        socket_info = sock_array[fileno]

                        if (event & 0x_0001) == 0x_0001:
                            # Socket is readable.
                            task_info = socket_info.recv_task_info

                            if task_info is None:
                                # No task awaits for socket to become readable.
                                # Mark as readale.
                                socket_info.recv_ready = True

                                # Note that socket may be registered for writing notification.
                                socket_info.event_mask &= 0x_FFFE # ~0x_0001

                                if socket_info.event_mask == 0:
                                    socket_epoll.unregister(fileno)
                                else:
                                    socket_epoll.modify(fileno, socket_info.event_mask)

                                socket_recv_count -= 1
                            else:
                                # Unbind task and socket.
                                task_info.recv_fileno = None
                                socket_info.recv_task_info = None

                                if task_info.yield_func == SYSCALL_SOCKET_ACCEPT:
                                    # Accept as many connections as possible.
                                    sock, nursery, handler_factory = task_info.yield_args

                                    try:
                                        while True:
                                            client_socket, client_address = sock.accept()
                                            handler = handler_factory(socket(sock=client_socket), client_address)
                                            handler_task_info = _TaskInfo(handler, task_info, nursery)
                                            task_deque.append(handler_task_info)
                                    except error:
                                        pass

                                    task_deque.append(task_info)

                                    del handler_task_info
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
                                    task_deque.append(task_info)

                                    del data
                                    del size
                                    del sock
                                elif task_info.yield_func == SYSCALL_SOCKET_RECV_INTO:
                                    # Receive data.
                                    sock, data, size = task_info.yield_args
                                    size = sock.recv_into(data, size)
                                    # Enqueue task.
                                    task_info.send_args = size
                                    task_deque.append(task_info)

                                    del data
                                    del size
                                    del sock
                                elif task_info.yield_func == SYSCALL_SOCKET_RECVFROM:
                                    # Receive data.
                                    sock, size = task_info.yield_args
                                    data, addr = sock.recvfrom(size)
                                    # Enqueue task.
                                    task_info.send_args = data, addr
                                    task_deque.append(task_info)

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
                                    task_deque.append(task_info)

                                    del addr
                                    del size
                                    del data
                                    del sock
                                else:
                                    raise Exception(f'Unexpected syscall {task_info.yield_func}.')

                        if (event & 0x_0004) == 0x_0004:
                            # Socket is writable.
                            task_info = socket_info.send_task_info

                            if task_info is None:
                                # No task awaits for socket to become writable.
                                # Mark as writable.
                                socket_info.send_ready = True

                                # Note that socket may be registered for reading notification.
                                socket_info.event_mask &= 0x_FFFB # ~0x_0004

                                if socket_info.event_mask == 0:
                                    socket_epoll.unregister(fileno)
                                else:
                                    socket_epoll.modify(fileno, socket_info.event_mask)

                                socket_send_count -= 1
                            else:
                                # Unbind task and socket.
                                task_info.send_fileno = None
                                socket_info.send_task_info = None

                                if task_info.yield_func == SYSCALL_SOCKET_CLOSE:
                                    # Close socket.
                                    # Is socket registered for reading notification?
                                    if socket_info.event_mask & 0x_0001 == 0x_0001:
                                        socket_recv_count -= 1

                                    # Is socket registered for writing notification?
                                    if socket_info.event_mask & 0x_0004 == 0x_0004:
                                        socket_send_count -= 1

                                    socket_epoll.unregister(fileno)

                                    sock = task_info.yield_args[0]

                                    # Close socket and reset socket info.
                                    sock.close()
                                    socket_info.recv_task_info = None
                                    socket_info.recv_ready = False
                                    socket_info.send_ready = False
                                    socket_info.event_mask = 0

                                    del sock
                                elif task_info.yield_func == SYSCALL_SOCKET_CONNECT:
                                    # TODO: SYSCALL_SOCKET_CONNECT is not implemented yet.
                                    pass
                                elif task_info.yield_func == SYSCALL_SOCKET_SEND:
                                    # Send data.
                                    sock, data = task_info.yield_args
                                    size = sock.send(data)
                                    # Enqueue task.
                                    task_info.send_args = size
                                    task_deque.append(task_info)

                                    del data
                                    del size
                                elif task_info.yield_func == SYSCALL_SOCKET_SENDTO:
                                    # Send data.
                                    sock, data, addr = task_info.yield_args
                                    size = sock.sendto(data, addr)
                                    # Enqueue task.
                                    task_info.send_args = size
                                    task_deque.append(task_info)

                                    del size
                                    del addr
                                    del data
                                    del sock
                                elif task_info.yield_func == SYSCALL_SOCKET_SHUTDOWN:
                                    # TODO: SYSCALL_SOCKET_SHUTDOWN is not implemented yet.
                                    pass
                                else:
                                    raise Exception(f'Unexpected syscall {task_info.yield_func}.')
                # Are there task which are scheduled to run later?
                elif len(time_heapq) > 0:
                    # First task in queue.
                    moment, task_info = time_heapq[0]

                    # Is task scheduled to run later?
                    if moment - now >= 0.001:
                        # Do not wait too much, ler loop cycle.
                        timeout = moment - now

                        if timeout > 0.01:
                            time_sleep(0.01)
                        else:
                            time_sleep(timeout)

                        del timeout

                    # Run all tasks which are ready to run.
                    while (len(time_heapq) > 0) and (time_heapq[0][0] <= moment):
                        _, task_info = heappop(time_heapq)
                        task_deque.append(task_info)

                    del task_info
                    del moment
                else:
                    # Nothing to do, stop loop.
                    running = False
            except Exception:
                print_exc()


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


@coroutine
def sleep(delay):
    yield SYSCALL_TASK_SLEEP, delay


_SOCKET_KINDS = {
    'tcp4': (AF_INET,  SOCK_STREAM, IPPROTO_TCP),
    'udp4': (AF_INET,  SOCK_DGRAM,  IPPROTO_UDP),
    'tcp6': (AF_INET6, SOCK_STREAM, IPPROTO_TCP),
    'udp6': (AF_INET6, SOCK_STREAM, IPPROTO_UDP),
}


class socket(object):
    def __init__(self, kind_name='tcp4', sock=None):
        from socket import socket as _socket

        kind = _SOCKET_KINDS[kind_name]

        if sock is None:
            self._socket = _socket(kind[0], kind[1], kind[2])
            self._socket.setblocking(0)
        else:
            self._socket = sock

    def __get_reuse_addr(self):
        return bool(self._socket.getsockopt(SOL_SOCKET, SO_REUSEADDR))

    def __set_reuse_addr(self, value):
        return self._socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1 if value else 0)

    def __get_reuse_port(self):
        return bool(self._socket.getsockopt(SOL_SOCKET, SO_REUSEPORT))

    def __set_reuse_port(self, value):
        return self._socket.setsockopt(SOL_SOCKET, SO_REUSEPORT, 1 if value else 0)

    reuse_addr = property(__get_reuse_addr, __set_reuse_addr)
    reuse_port = property(__get_reuse_port, __set_reuse_port)

    def bind(self, addr):
        self._socket.bind(addr)

    @coroutine
    def accept(self, nursery, handler_factory):
        return (yield SYSCALL_SOCKET_ACCEPT, self._socket, nursery, handler_factory)

    @coroutine
    def close(self):
        return (yield SYSCALL_SOCKET_CLOSE, self._socket)

    @coroutine
    def connect(self, addr):
        return (yield SYSCALL_SOCKET_CONNECT, self._socket, addr)

    @coroutine
    def listen(self, backlog):
        self._socket.listen(backlog)

    @coroutine
    def recv(self, size):
        return (yield SYSCALL_SOCKET_RECV, self._socket, size)

    @coroutine
    def recv_into(self, data, size):
        return (yield SYSCALL_SOCKET_RECV_INTO, self._socket, data, size)

    @coroutine
    def recvfrom(self, size):
        return (yield SYSCALL_SOCKET_RECVFROM, self._socket, size)

    @coroutine
    def recvfrom_into(self, data, size):
        return (yield SYSCALL_SOCKET_RECVFROM_INTO, self._socket, data, size)

    @coroutine
    def send(self, data):
        return (yield SYSCALL_SOCKET_SEND, self._socket, data)

    @coroutine
    def sendto(self, data, addr):
        return (yield SYSCALL_SOCKET_SENDTO, self._socket, data, addr)

    @coroutine
    def shutdown(self, how):
        return (yield SYSCALL_SOCKET_SHUTDOWN, self._socket, how)

