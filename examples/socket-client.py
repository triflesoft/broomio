#!/usr/bin/env python3

from broomio import Loop
from broomio import Nursery
from broomio import sleep
from broomio import socket
from traceback import print_exc


async def connector():
    client_socket = socket()

    try:
        await client_socket.connect(('python.org', 80))
        await client_socket.send(b'GET / HTTP/1.1\r\nHost: python.org\r\n\r\n')
        data = await client_socket.recv(1024)
        await client_socket.close()
        print(data.decode('ascii'))
    except Exception:
        print_exc()


loop = Loop()
loop.start_soon(connector())
loop.run()

