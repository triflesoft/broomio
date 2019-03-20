epoll / poll
============

Fortunately values of EPOLL* and POLL* are equal in Linux.

- EPOLLIN / POLLIN == 0x_0001
    The associated file is available for read(2) operations.

- EPOOLPRI / POLLPRI == 0x_0002
    TODO: Process POOLPRI event.
    There is some exceptional condition on the file descriptor. Possibilities include:

    - There is out-of-band data on a TCP socket (see tcp(7)).
    - A pseudoterminal master in packet mode has seen a state change on the slave (see ioctl_tty(2)).
    - A cgroup.events file has been modified (see cgroups(7)).

- EPOLLOUT / POLLOUT == 0x_0004
    The associated file is available for write(2) operations.

- EPOLLERR / POLLERR == 0x_0008
    TODO: Process POLLERR event.
    Error condition happened on the associated file descriptor. This event is also reported for the write end of a pipe when the read end has been closed.  epoll_wait(2) will always report for this event; it is not necessary to set it in events.

- EPOLLHUP / POLLHUP == 0x_0010
    TODO: Process POLLHUP event.
    Hang up happened on the associated file descriptor. epoll_wait(2) will always wait for this event; it is not necessary to set it in events. Note that when reading from a channel such as a pipe or a stream socket, this event merely indicates that the peer closed its end of the channel. Subsequent reads from the channel will return 0 (end of file) only after all outstanding data in the channel has been consumed.

- EPOLLRDHUP / POLLRDHUP == 0x_2000
    TODO: Process POLLRDHUP event.
    Stream socket peer closed connection, or shut down writing half of connection.  (This flag is especially useful for writing simple code to detect peer shutdown when using Edge Triggered monitoring.)

- EPOLLRDNORM / POLLRDNORM == 0x_0040

- EPOLLRDBAND / POLLRDBAND == 0x_0080

- EPOLLWRNORM / POLLWRNORM == 0x_0100

- EPOLLWRBAND / POLLWRBAND == 0x_0200

- EPOLLMSG / POLLMSG == 0x_0400
