#!/usr/bin/env python3

from httptools import HttpRequestParser
from broomio import Loop
from broomio import Nursery
from broomio import TcpClientSocket
from broomio import UnixListenSocket


class RequestParserCallback:
    def __init__(self):
        self.url = b''
        self.headers = {}
        self.are_headers_complete = False
        self.body = b''
        self.is_body_complete = False

    def on_message_begin(self):
        pass

    def on_url(self, url: bytes):
        self.url = url

    def on_header(self, name: bytes, value: bytes):
        self.headers[name.upper()] = value

    def on_headers_complete(self):
        self.are_headers_complete = True

    def on_body(self, body: bytes):
        self.body += body

    def on_message_complete(self):
        self.is_body_complete = True


async def connection_handler(unix_server_socket, client_address):
    callback = RequestParserCallback()
    parser = HttpRequestParser(callback)
    request_data = b''

    try:
        while not callback.is_body_complete:
            chunk = await unix_server_socket.recv(1024)

            if len(chunk) == 0:
                await unix_server_socket.close()
                return

            request_data += chunk
            parser.feed_data(chunk)

        host = callback.headers[b'HOST']

        if b':' in host:
            host, port = host.split(b':')
            port = int(port)
        else:
            port = 80

        tcp_client_socket = TcpClientSocket()

        await tcp_client_socket.connect((host, port))

        try:
            while len(request_data) > 0:
                length = await tcp_client_socket.send(request_data)
                request_data = request_data[length:]

            while True:
                chunk = await tcp_client_socket.recv(1024)

                if len(chunk) == 0:
                    break

                await unix_server_socket.send(chunk)
        finally:
            await tcp_client_socket.close()
    finally:
        await unix_server_socket.close()

async def listener():
    unix_listen_socket = UnixListenSocket()
    unix_listen_socket.reuse_addr = True
    unix_listen_socket.reuse_port = True
    unix_listen_socket.bind('/tmp/http-proxy')
    await unix_listen_socket.listen(1024)

    async with Nursery() as nursery:
        while True:
            await unix_listen_socket.accept(nursery, connection_handler)


if __name__ == '__main__':
    loop = Loop()
    loop.start_soon(listener())
    loop.run()
