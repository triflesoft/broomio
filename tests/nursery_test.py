#!/usr/bin/env python3

from broomio import Loop
from broomio import Nursery
from broomio import NurseryError
from broomio import NurseryExceptionPolicy
from broomio import sleep
from math import fabs
from time import time
from tracemalloc import start
from unittest import main
from unittest import TestCase


start(4)


class TestNursery(TestCase):
    def test_exception_policy(self):
        async def child(s, x, y):
            z = x / y

        async def parent(vars, exception_policy):
            try:
                async with Nursery(exception_policy) as nursery:
                    await nursery.start_soon(child(0.01, 1, 2))
                    await nursery.start_soon(child(0.0, 1, 0))
                    await nursery.start_soon(child(0.02, 1, 2))
                    await nursery.start_soon(child(0.0, 1, 0))
                    await nursery.start_soon(child(0.03, 1, 2))
                    await nursery.start_soon(child(0.0, 1, 0))
                    await nursery.start_soon(child(0.04, 1, 2))
            except NurseryError as ne:
                vars['exception_number'] = len(ne.exceptions)

        vars = {}
        loop = Loop()
        loop.start_soon(parent(vars, NurseryExceptionPolicy.Abort))
        loop.run()
        self.assertEqual(vars['exception_number'], 1)

        vars = {}
        loop = Loop()
        loop.start_soon(parent(vars, NurseryExceptionPolicy.Accumulate))
        loop.run()
        self.assertEqual(vars['exception_number'], 3)

        vars = {}
        loop = Loop()
        loop.start_soon(parent(vars, NurseryExceptionPolicy.Ignore))
        loop.run()
        self.assertNotIn('exception_number', vars)


if __name__ == '__main__':
    main()

