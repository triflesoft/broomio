#!/usr/bin/env python3

from tracemalloc import start
from unittest import main
from unittest import TestCase
from broomio import Loop
from broomio import sleep


start(4)


class TestScheduler(TestCase):
    def test_scheduler(self):
        async def child(index):
            await sleep(index / 10.0)
            order.append(index)

        order = []

        loop = Loop(execution_order='FIFO')

        for index in range(10):
            loop.start_soon(child(index))

        loop.run()

        self.assertEqual(order, [index for index in range(10)])

        order = []

        loop = Loop(execution_order='LIFO')

        for index in range(10):
            loop.start_soon(child(index))

        loop.run()

        self.assertEqual(order, [index for index in range(10)])

if __name__ == '__main__':
    main()

