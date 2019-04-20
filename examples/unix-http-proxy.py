#!/usr/bin/env python3

from broomio import Loop
from broomio import Nursery
from broomio import sleep
from broomio import socket
from datetime import datetime
from httptools import HttpRequestParser
from jinja2 import Environment
from jinja2 import FileSystemLoader
from os.path import dirname


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


async def connection_handler(client_socket, client_address):
    callback = RequestParserCallback()
    parser = HttpRequestParser(callback)
    request_data = b''

    try:
        while not callback.is_body_complete:
            chunk = await client_socket.recv(1024)

            if len(chunk) == 0:
                await client_socket.close()
                return

            request_data += chunk
            parser.feed_data(chunk)

        host = callback.headers[b'HOST']

        if b':' in host:
            host, port = host.split(b':')
            port = int(port)
        else:
            port = 80

        upstream_socket = socket('tcp4')

        await upstream_socket.connect((host, port))

        try:
            while len(request_data) > 0:
                length = await upstream_socket.send(request_data)
                request_data = request_data[length:]

            while True:
                chunk = await upstream_socket.recv(1024)

                if len(chunk) == 0:
                    break

                await client_socket.send(chunk)
        finally:
            await upstream_socket.close()
    finally:
        await client_socket.close()

async def listener():
    server_socket = socket('unix')
    server_socket.reuse_addr = True
    server_socket.reuse_port = True
    server_socket.bind('/tmp/http-proxy')
    await server_socket.listen(1024)

    async with Nursery() as nursery:
        while True:
            await server_socket.accept(nursery, connection_handler)


loop = Loop()
loop.start_soon(listener())
loop.run()
