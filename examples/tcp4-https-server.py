#!/usr/bin/env python3

from datetime import datetime
from jinja2 import Environment
from jinja2 import FileSystemLoader
from os.path import dirname
from os.path import join
from ssl import PROTOCOL_TLS_SERVER
from ssl import SSLContext
from ssl import SSLError
from httptools import HttpRequestParser
from broomio import Loop
from broomio import Nursery
from broomio import TcpListenSocket
from broomio import TlsSocket


HEAD_TEMPLATE = b'''HTTP/1.1 200 OK
Date: Mon, 13 Jan 2019 12:28:53 GMT
Server: Apache/2.2.14 (Win32)
Last-Modified: Wed, 22 Jul 2009 19:15:56 GMT
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


context = SSLContext(PROTOCOL_TLS_SERVER)
context.load_cert_chain(
    join(dirname(__file__), 'localhost.crt'),
    join(dirname(__file__), 'localhost.key'),
    password='p@$$w0rd')


async def connection_handler(tcp_server_socket, client_address):
    callback = RequestParserCallback()
    parser = HttpRequestParser(callback)
    keep_alive = True

    tls_server_socket = TlsSocket(tcp_server_socket, context, 'localhost')

    try:
        await tls_server_socket.handshake()

        while keep_alive:
            callback.reset()

            while not callback.is_body_complete:
                chunk = await tls_server_socket.recv(1024)

                if len(chunk) == 0:
                    raise BrokenPipeError()

                parser.feed_data(chunk)

            keep_alive = parser.should_keep_alive()
            template = environment.get_template('http-server.html')
            body_text = template.render({'address': client_address, 'datetime': datetime.now()})
            body_data = body_text.encode('utf-8')
            response = (HEAD_TEMPLATE % (len(body_data), b'Keep-Alive' if keep_alive else b'Closed')).replace(b'\n', b'\r\n') + body_data

            while len(response) > 0:
                length = await tls_server_socket.send(response)
                response = response[length:]

        await tls_server_socket.close()
    except (ConnectionError, SSLError):
        pass

    await tcp_server_socket.close()


async def listener():
    listen_socket = TcpListenSocket()
    listen_socket.reuse_addr = True
    listen_socket.reuse_port = True
    listen_socket.bind(('0.0.0.0', 7777))
    await listen_socket.listen(1024)

    async with Nursery() as nursery:
        while True:
            await listen_socket.accept(nursery, connection_handler)


if __name__ == '__main__':
    loop = Loop()
    loop.start_soon(listener())
    loop.run()
