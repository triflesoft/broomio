SYSCALL_TASK_SLEEP           = 0x_01 # Sleep for specified in seconds delay.
SYSCALL_NURSERY_INIT         = 0x_11 # Create new nursery.
SYSCALL_NURSERY_JOIN         = 0x_12 # Wait for all tasks in nursery to complete.
SYSCALL_NURSERY_KILL         = 0x_13 # Kill all tasks in nursery.
SYSCALL_NURSERY_START_SOON   = 0x_14 # Start task in nursery in current tick.
SYSCALL_NURSERY_START_LATER  = 0x_15 # Start task in nursery after specified in seconds delay.
SYSCALL_SOCKET_ACCEPT        = 0x_51 # Accept as many connections as possible.
SYSCALL_SOCKET_CLOSE         = 0x_52 # Close socket canceling all tasks waiting for the socket.
SYSCALL_SOCKET_CONNECT       = 0x_53 # Connect to IP endpoint.
SYSCALL_SOCKET_LISTEN        = 0x_54 # Listen on IP endpoint.
SYSCALL_SOCKET_RECV          = 0x_55 # Receive data.
SYSCALL_SOCKET_RECV_INTO     = 0x_56 # Receive data.
SYSCALL_SOCKET_RECVFROM      = 0x_57 # Receive data.
SYSCALL_SOCKET_RECVFROM_INTO = 0x_58 # Receive data.
SYSCALL_SOCKET_SEND          = 0x_59 # Send data.
SYSCALL_SOCKET_SENDTO        = 0x_5A # Send data.
SYSCALL_SOCKET_SHUTDOWN      = 0x_5B # Shutdown socket.
