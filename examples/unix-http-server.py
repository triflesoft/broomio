#!/usr/bin/env python3

from broomio import Loop
from broomio import Nursery
from broomio import sleep
from broomio import UnixListenSocket
from datetime import datetime
from httptools import HttpRequestParser
from jinja2 import Environment
from jinja2 import FileSystemLoader
from os.path import dirname


HEAD_TEMPLATE = b'''HTTP/1.1 200 OK
Date: Mon, 13 Jan 2019 12:28:53 GMT
Server: Apache/2.2.14 (Win32)
Last-Modified: Wed, 22 Jul 2009 19:15:56 GMT
Content-Length: %d
Content-Type: text/html
Connection: Closed

'''

environment = Environment(auto_reload=False, enable_async=False, loader=FileSystemLoader(dirname(__file__)))

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
        self.headers[name] = value

    def on_headers_complete(self):
        self.are_headers_complete = True

    def on_body(self, body: bytes):
        self.body += body

    def on_message_complete(self):
        self.is_body_complete = True


async def connection_handler(unix_server_socket, client_address):
    callback = RequestParserCallback()
    parser = HttpRequestParser(callback)

    while not callback.is_body_complete:
        chunk = await unix_server_socket.recv(1024)

        if len(chunk) == 0:
            await unix_server_socket.close()
            return

        parser.feed_data(chunk)

    template = environment.get_template('http-server.html')
    body_text = template.render({'address': unix_server_socket.peer_cred, 'datetime': datetime.now()})
    body_data = body_text.encode('utf-8')
    response = (HEAD_TEMPLATE % len(body_data)) + body_data

    while len(response) > 0:
        length = await unix_server_socket.send(response)
        response = response[length:]

    await unix_server_socket.close()


async def listener():
    unix_listen_socket = UnixListenSocket()
    unix_listen_socket.reuse_addr = True
    unix_listen_socket.reuse_port = True
    unix_listen_socket.bind('/tmp/http-server')
    await unix_listen_socket.listen(1024)

    async with Nursery() as nursery:
        while True:
            await unix_listen_socket.accept(nursery, connection_handler)


loop = Loop()
loop.start_soon(listener())
loop.run()
