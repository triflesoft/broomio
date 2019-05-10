SYSCALL_TASK_SLEEP           = 'TASK_SLEEP'           if __debug__ else 0x_01 # Sleep for specified in seconds delay. pylint: disable=C0326
SYSCALL_NURSERY_INIT         = 'NURSERY_INIT'         if __debug__ else 0x_11 # Create new nursery. pylint: disable=C0326
SYSCALL_NURSERY_JOIN         = 'NURSERY_JOIN'         if __debug__ else 0x_12 # Wait for all tasks in nursery to complete. pylint: disable=C0326
SYSCALL_NURSERY_KILL         = 'NURSERY_KILL'         if __debug__ else 0x_13 # Kill all tasks in nursery. pylint: disable=C0326
SYSCALL_NURSERY_START_SOON   = 'NURSERY_START_SOON'   if __debug__ else 0x_14 # Start task in nursery in current tick. pylint: disable=C0326
SYSCALL_NURSERY_START_LATER  = 'NURSERY_START_LATER'  if __debug__ else 0x_15 # Start task in nursery after specified in seconds delay. pylint: disable=C0326
SYSCALL_SOCKET_ACCEPT        = 'SOCKET_ACCEPT'        if __debug__ else 0x_31 # Accept as many connections as possible. pylint: disable=C0326
SYSCALL_SOCKET_CLOSE         = 'SOCKET_CLOSE'         if __debug__ else 0x_32 # Close socket canceling all tasks waiting for the socket. pylint: disable=C0326
SYSCALL_SOCKET_CONNECT       = 'SOCKET_CONNECT'       if __debug__ else 0x_33 # Connect to IP endpoint. pylint: disable=C0326
SYSCALL_SOCKET_LISTEN        = 'SOCKET_LISTEN'        if __debug__ else 0x_34 # Listen on IP endpoint. pylint: disable=C0326
SYSCALL_SOCKET_RECV          = 'SOCKET_RECV'          if __debug__ else 0x_35 # Receive data. pylint: disable=C0326
SYSCALL_SOCKET_RECV_INTO     = 'SOCKET_RECV_INTO'     if __debug__ else 0x_36 # Receive data. pylint: disable=C0326
SYSCALL_SOCKET_RECVFROM      = 'SOCKET_RECVFROM'      if __debug__ else 0x_37 # Receive data. pylint: disable=C0326
SYSCALL_SOCKET_RECVFROM_INTO = 'SOCKET_RECVFROM_INTO' if __debug__ else 0x_38 # Receive data. pylint: disable=C0326
SYSCALL_SOCKET_SEND          = 'SOCKET_SEND'          if __debug__ else 0x_39 # Send data. pylint: disable=C0326
SYSCALL_SOCKET_SENDTO        = 'SOCKET_SENDTO'        if __debug__ else 0x_3A # Send data. pylint: disable=C0326
SYSCALL_SOCKET_SHUTDOWN      = 'SOCKET_SHUTDOWN'      if __debug__ else 0x_3B # Shutdown socket. pylint: disable=C0326
SYSCALL_POOL_EXECUTE         = 'POOL_EXECUTE'         if __debug__ else 0x_51 # Execute task in pool. pylint: disable=C0326
