#!/usr/bin/env python3

from broomio import Loop
from broomio import Nursery
from broomio import sleep
from math import fabs
from time import time
from tracemalloc import start
from unittest import main
from unittest import TestCase


start(4)


class TestScheduler(TestCase):
    def test_scheduler(self):
        order = []

        async def child(index):
            await sleep(index / 10.0)
            order.append(index)

        loop = Loop()

        for index in range(10):
            loop.start_soon(child(index))

        loop.run()

        self.assertEqual(order, [index for index in range(10)])

if __name__ == '__main__':
    main()

