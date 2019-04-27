#!/usr/bin/env python3

from broomio import Loop
from broomio import TcpClientSocket
from broomio import TlsSocket
from httptools import HttpResponseParser
from pprint import pprint
from ssl import PROTOCOL_TLS_CLIENT
from ssl import SSLContext
from traceback import print_exc


class ResponseParserCallback:
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


async def connector():
    tcp_client_socket = TcpClientSocket()
    callback = ResponseParserCallback()
    parser = HttpResponseParser(callback)
    server_hostname = 'www.python.org'

    try:
        await tcp_client_socket.connect((server_hostname, 443))

        context = SSLContext(PROTOCOL_TLS_CLIENT)
        context.load_default_certs()

        tls_client_socket = TlsSocket(tcp_client_socket, context, server_hostname)
        await tls_client_socket.handshake()

        print(f'NPN Protocol: {tls_client_socket._object.selected_npn_protocol()}')
        print(f'Cipher:       {tls_client_socket._object.cipher()}')
        print(f'Compression:  {tls_client_socket._object.compression()}')
        print('Peer Certificate:')
        pprint(tls_client_socket._object.getpeercert())
        print()

        await tls_client_socket.send(f'GET / HTTP/1.1\r\nHost: {server_hostname}\r\n\r\n'.encode('ascii'))

        while not callback.is_body_complete:
            chunk = await tls_client_socket.recv(65536)

            parser.feed_data(chunk)

        await tls_client_socket.close()
        await tcp_client_socket.close()

        pprint(callback.headers)
        print()
        print(f'Status: {parser.get_status_code()}')
        print('Body:')
        print(callback.body.decode('utf-8'))
    except Exception:
        print_exc()


loop = Loop()
loop.start_soon(connector())
loop.run()

