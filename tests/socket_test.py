from broomio import Loop
from broomio import Nursery
from broomio import sleep
from broomio import socket
from unittest import main
from unittest import TestCase


class TestSocket(TestCase):
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

