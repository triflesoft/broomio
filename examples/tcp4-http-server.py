#!/usr/bin/env python3

from datetime import datetime
from datetime import timezone
from email.utils import format_datetime
from jinja2 import Environment
from jinja2 import FileSystemLoader
from os.path import dirname
from httptools import HttpRequestParser
from broomio import Loop
from broomio import Nursery
from broomio import TcpListenSocket


HEAD_TEMPLATE = b'''HTTP/1.1 200 OK
Date: %s
Server: broomio/1.2.3
Content-Length: %d
Content-Type: text/html
Connection: %s

'''

environment = Environment(auto_reload=False, enable_async=False, loader=FileSystemLoader(dirname(__file__)))


class RequestParserCallback:
    def __init__(self):
        self.url = b''
        self.headers = {}
        self.are_headers_complete = False
        self.body = b''
        self.is_body_complete = False

    def reset(self):
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
        self.headers[name] = value

    def on_headers_complete(self):
        self.are_headers_complete = True

    def on_body(self, body: bytes):
        self.body += body

    def on_message_complete(self):
        self.is_body_complete = True


async def connection_handler(tcp_server_socket, client_address):
    callback = RequestParserCallback()
    parser = HttpRequestParser(callback)
    keep_alive = True

    try:
        while keep_alive:
            callback.reset()

            while not callback.is_body_complete:
                chunk = await tcp_server_socket.recv(1024)

                if len(chunk) == 0:
                    raise BrokenPipeError()

                parser.feed_data(chunk)

            keep_alive = parser.should_keep_alive()
            template = environment.get_template('http-server.html')
            body_text = template.render({'address': client_address, 'datetime': datetime.now()})
            body_data = body_text.encode('utf-8')
            response = (HEAD_TEMPLATE % (
                format_datetime(datetime.now(timezone.utc), True).encode('ascii'),
                len(body_data),
                b'Keep-Alive' if keep_alive else b'Closed')) + body_data

            while len(response) > 0:
                length = await tcp_server_socket.send(response)
                response = response[length:]
    except ConnectionError:
        pass

    await tcp_server_socket.close()


async def listener():
    tcp_listen_socket = TcpListenSocket()
    tcp_listen_socket.reuse_addr = True
    tcp_listen_socket.reuse_port = True
    tcp_listen_socket.bind(('0.0.0.0', 7777))
    await tcp_listen_socket.listen(1024)

    async with Nursery() as nursery:
        while True:
            await tcp_listen_socket.accept(nursery, connection_handler)


if __name__ == '__main__':
    loop = Loop()
    loop.start_soon(listener())
    loop.run()
