#!/usr/bin/env python3

from broomio import Loop
from broomio import Nursery
from broomio import sleep
from broomio import TcpClientSocket
from broomio import TcpListenSocket
from broomio import UdpSocket
from broomio import UnixClientSocket
from broomio import UnixListenSocket
from socket import AF_INET
from socket import AF_INET6
from socket import AF_UNIX
from socket import SOCK_DGRAM
from socket import SOCK_STREAM
from time import time
from tracemalloc import start
from unittest import main
from unittest import TestCase


start(4)


class TestSocket(TestCase):
    def test_socket_attributes(self):
        async def create():
            tcp_client_socket_4 = TcpClientSocket(4)
            self.assertEqual(tcp_client_socket_4._socket.family, AF_INET)
            self.assertEqual(tcp_client_socket_4._socket.type, SOCK_STREAM)
            tcp_listen_socket_4 = TcpListenSocket(4)
            self.assertEqual(tcp_listen_socket_4._socket.family, AF_INET)
            self.assertEqual(tcp_listen_socket_4._socket.type, SOCK_STREAM)

            tcp_client_socket_6 = TcpClientSocket(6)
            self.assertEqual(tcp_client_socket_6._socket.family, AF_INET6)
            self.assertEqual(tcp_client_socket_6._socket.type, SOCK_STREAM)
            tcp_listen_socket_6 = TcpListenSocket(6)
            self.assertEqual(tcp_listen_socket_6._socket.family, AF_INET6)
            self.assertEqual(tcp_listen_socket_6._socket.type, SOCK_STREAM)

            unix_client_socket = UnixClientSocket()
            self.assertEqual(unix_client_socket._socket.family, AF_UNIX)
            self.assertEqual(unix_client_socket._socket.type, SOCK_STREAM)
            unix_listen_socket = UnixListenSocket()
            self.assertEqual(unix_listen_socket._socket.family, AF_UNIX)
            self.assertEqual(unix_listen_socket._socket.type, SOCK_STREAM)

            udp_socket_4 = UdpSocket(4)
            self.assertEqual(udp_socket_4._socket.family, AF_INET)
            self.assertEqual(udp_socket_4._socket.type, SOCK_DGRAM)

            udp_socket_6 = UdpSocket(6)
            self.assertEqual(udp_socket_6._socket.family, AF_INET6)
            self.assertEqual(udp_socket_6._socket.type, SOCK_DGRAM)

            await tcp_client_socket_4.close()
            await tcp_listen_socket_4.close()
            await tcp_client_socket_6.close()
            await tcp_listen_socket_6.close()
            await unix_client_socket.close()
            await unix_listen_socket.close()
            await udp_socket_4.close()
            await udp_socket_6.close()

        loop = Loop()
        loop.start_soon(create())
        loop.run()

    def test_socket_timeout(self):
        async def client_connect(vars):
            vars['enter'] = time()

            tcp_client_socket = TcpClientSocket()

            async with Nursery(timeout=1):
                try:
                    await tcp_client_socket.connect(('169.254.0.1', 65534))
                except BaseException:
                    pass
                finally:
                    await tcp_client_socket.close()

            vars['exit'] = time()

        vars = {}
        loop = Loop()
        loop.start_soon(client_connect(vars))
        loop.run()

        self.assertAlmostEqual(vars['exit'] - vars['enter'], 1, 1)

    def test_socket_listen_connect(self):
        async def server_client_handler(tcp_server_socket, client_address):
            self.assertEqual(await tcp_server_socket.recv(1), b'A')
            await tcp_server_socket.send(b'B')
            await tcp_server_socket.close()

        async def server_listen():
            tcp_listen_socket = TcpListenSocket()
            tcp_listen_socket.reuse_addr = True
            tcp_listen_socket.bind(('127.0.0.1', 65533))
            await tcp_listen_socket.listen(1)

            async with Nursery() as nursery:
                await tcp_listen_socket.accept(nursery, server_client_handler)

            await tcp_listen_socket.close()

        async def client_connect():
            tcp_client_socket = TcpClientSocket()
            await sleep(0.01) # Make client start later, when server already listens.
            await tcp_client_socket.connect(('127.0.0.1', 65533))
            await tcp_client_socket.send(b'A')
            self.assertEqual(await tcp_client_socket.recv(1), b'B')
            await tcp_client_socket.close()

        loop = Loop()
        loop.start_soon(server_listen())
        loop.start_soon(client_connect())
        loop.run()

    def test_socket_shutdown(self):
        async def server_client_handler(tcp_server_socket, client_address):
            await tcp_server_socket.shutdown()

            with self.assertRaises(BrokenPipeError):
                await tcp_server_socket.send(b'B')

            await tcp_server_socket.close()

        async def server_listen():
            tcp_listen_socket = TcpListenSocket()
            tcp_listen_socket.reuse_addr = True
            tcp_listen_socket.bind(('127.0.0.1', 65532))
            await tcp_listen_socket.listen(1)

            async with Nursery() as nursery:
                await tcp_listen_socket.accept(nursery, server_client_handler)

            await tcp_listen_socket.close()

        async def client_connect():
            tcp_client_socket = TcpClientSocket()
            await sleep(0.01) # Make client start later, when server already listens.
            await tcp_client_socket.connect(('127.0.0.1', 65532))
            self.assertEqual(await tcp_client_socket.recv(1), b'')
            await tcp_client_socket.close()

        loop = Loop()
        loop.start_soon(server_listen())
        loop.start_soon(client_connect())
        loop.run()

    def test_socket_close(self):
        async def server_client_handler(client_socket2, client_address):
            self.assertEqual(await client_socket2.recv(1), b'C')
            self.assertEqual(await client_socket2.recv(1), b'')

            await client_socket2.close()

        async def server_listen():
            tcp_listen_socket = TcpListenSocket()
            tcp_listen_socket.reuse_addr = True
            tcp_listen_socket.bind(('127.0.0.1', 65531))
            await tcp_listen_socket.listen(1)

            async with Nursery() as nursery:
                await tcp_listen_socket.accept(nursery, server_client_handler)

            await tcp_listen_socket.close()

        async def client_connect():
            tcp_client_socket = TcpClientSocket()
            await sleep(0.01) # Make client start later, when server already listens.
            await tcp_client_socket.connect(('127.0.0.1', 65531))
            await tcp_client_socket.send(b'C')
            await tcp_client_socket.close()

        loop = Loop()
        loop.start_soon(server_listen())
        loop.start_soon(client_connect())
        loop.run()


if __name__ == '__main__':
    main()

