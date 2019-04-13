#!/usr/bin/env python3

from broomio import Loop
from broomio import Nursery
from broomio import sleep
from broomio import socket
from socket import AF_INET
from socket import AF_INET6
from socket import AF_UNIX
from socket import SOCK_DGRAM
from socket import SOCK_STREAM
from tracemalloc import start
from unittest import main
from unittest import TestCase


start(4)


class TestSocket(TestCase):
    def test_socket_attributes(self):
        async def create():
            tcp4_socket = socket('tcp4')
            self.assertEqual(tcp4_socket._socket.family, AF_INET)
            self.assertEqual(tcp4_socket._socket.type, SOCK_STREAM)
            tcp6_socket = socket('tcp6')
            self.assertEqual(tcp6_socket._socket.family, AF_INET6)
            self.assertEqual(tcp6_socket._socket.type, SOCK_STREAM)
            udp4_socket = socket('udp4')
            self.assertEqual(udp4_socket._socket.family, AF_INET)
            self.assertEqual(udp4_socket._socket.type, SOCK_DGRAM)
            udp6_socket = socket('udp6')
            self.assertEqual(udp6_socket._socket.family, AF_INET6)
            self.assertEqual(udp6_socket._socket.type, SOCK_DGRAM)
            unix_socket = socket('unix')
            self.assertEqual(unix_socket._socket.family, AF_UNIX)
            self.assertEqual(unix_socket._socket.type, SOCK_STREAM)

            await tcp4_socket.close()
            await tcp6_socket.close()
            await udp4_socket.close()
            await udp6_socket.close()
            await unix_socket.close()

        loop = Loop()
        loop.start_soon(create())
        loop.run()

    def test_socket_timeout(self):
        async def client_connect():
            client_socket = socket()

            try:
                #await client_socket.connect(('169.254.0.1', 65534))
                pass
            finally:
                await client_socket.close()

        loop = Loop()
        loop.start_soon(client_connect())
        loop.run()

    def test_socket_listen_connect(self):
        async def server_client_handler(client_socket2, client_address):
            self.assertEqual(await client_socket2.recv(1), b'A')
            await client_socket2.send(b'B')
            await client_socket2.close()

        async def server_listen():
            server_socket = socket()
            server_socket.reuse_addr = True
            server_socket.reuse_port = True
            server_socket.bind(('127.0.0.1', 33333))
            await server_socket.listen(1)

            async with Nursery() as nursery:
                await server_socket.accept(nursery, server_client_handler)

            await server_socket.close()

        async def client_connect():
            client_socket1 = socket()
            await sleep(0.01) # Make client start later, when server already listens.
            await client_socket1.connect(('127.0.0.1', 33333))
            await client_socket1.send(b'A')
            self.assertEqual(await client_socket1.recv(1), b'B')
            await client_socket1.close()

        loop = Loop()
        loop.start_soon(server_listen())
        loop.start_soon(client_connect())
        loop.run()


if __name__ == '__main__':
    main()

