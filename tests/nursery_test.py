#!/usr/bin/env python3

from tracemalloc import start
from unittest import main
from unittest import TestCase
from broomio import Loop
from broomio import Nursery
from broomio import NurseryError
from broomio import NurseryExceptionPolicy
from broomio import sleep


start(4)


class TestNursery(TestCase):
    def test_exception_policy(self):
        async def child(x, y):
            z = x / y
            del z

        async def parent_solid(vars, exception_policy):
            try:
                async with Nursery(exception_policy) as nursery:
                    await nursery.start_soon(child(1, 2))
                    await nursery.start_soon(child(1, 0))
                    await nursery.start_soon(child(1, 2))
                    await nursery.start_soon(child(1, 0))
                    await nursery.start_soon(child(1, 2))
                    await nursery.start_soon(child(1, 0))
                    await nursery.start_soon(child(1, 2))
            except NurseryError as ne:
                vars['exception_number'] = len(ne._exception_infos)

        async def parent_split(vars, exception_policy):
            try:
                async with Nursery(exception_policy) as nursery:
                    await nursery.start_soon(child(1, 2))
                    await nursery.start_soon(child(1, 0))
                    await nursery.start_soon(child(1, 2))
                    await sleep(0.1)
                    await nursery.start_soon(child(1, 0))
                    await nursery.start_soon(child(1, 2))
                    await nursery.start_soon(child(1, 0))
                    await nursery.start_soon(child(1, 2))
            except NurseryError as ne:
                vars['exception_number'] = len(ne._exception_infos)

        for params in [
            ('FIFO', NurseryExceptionPolicy.Abort, 1),
            ('LIFO', NurseryExceptionPolicy.Abort, 1),
            ('FIFO', NurseryExceptionPolicy.Accumulate, 3),
            ('LIFO', NurseryExceptionPolicy.Accumulate, 3),
            ('FIFO', NurseryExceptionPolicy.Ignore, None),
            ('LIFO', NurseryExceptionPolicy.Ignore, None)]:
            with self.subTest(execution_order=params[0], policy=params[1]):
                vars = {'exception_number': None}
                loop = Loop(execution_order=params[0])
                loop.start_soon(parent_solid(vars, params[1]))
                loop.run()
                self.assertEqual(vars['exception_number'], params[2])

        for params in [
            ('FIFO', NurseryExceptionPolicy.Abort, 1),
            ('LIFO', NurseryExceptionPolicy.Abort, 1),
            ('FIFO', NurseryExceptionPolicy.Accumulate, 3),
            ('LIFO', NurseryExceptionPolicy.Accumulate, 3),
            ('FIFO', NurseryExceptionPolicy.Ignore, None),
            ('LIFO', NurseryExceptionPolicy.Ignore, None)]:
            with self.subTest(execution_order=params[0], policy=params[1]):
                vars = {'exception_number': None}
                loop = Loop(execution_order=params[0])
                loop.start_soon(parent_split(vars, params[1]))
                loop.run()
                self.assertEqual(vars['exception_number'], params[2])


    def test_exception_handling(self):
        async def child(vars, delay):
            vars['count_enter'] += 1
            await sleep(delay)
            vars['count_exit'] += 1

        async def parent(vars):
            vars['count_enter'] = 0
            vars['count_exit'] = 0

            try:
                async with Nursery() as nursery:
                    await nursery.start_soon(child(vars, 0.1))
                    await nursery.start_soon(child(vars, 0.3))
                    await sleep(0.2)
                    raise Exception("STOP ALL")
            except Exception:
                pass

        for params in [
            ('FIFO', ),
            ('LIFO', )]:
            with self.subTest(execution_order=params[0]):
                vars = {}
                loop = Loop(execution_order=params[0])
                loop.start_soon(parent(vars))
                loop.run()
                self.assertEqual(vars['count_enter'], 2)
                self.assertEqual(vars['count_exit'], 1)

    def test_nested_exception_handling(self):
        # Execution timeline \
        #      0.0 0.1 0.2 0.3 0.4 0.5 0.6 \
        # 1a    |***|***|***|***!***|   | \
        # 1a/2a |   |***|***|***!***|   | \
        # 1a/2b |   |***|   |   !   |   | \
        # 1b    |   |***|***|***!***|***| \
        # 1b/2c |   |   |***|***!***|***| \
        # 1b/2c |   |   |***|   !   |   | \
        # Execution will be interrupted at 0.4s, thus there should be 6 enters and 2 exits.
        async def child2(vars, delay):
            vars['count_enter'] += 1
            await sleep(delay)
            vars['count_exit'] += 1

        async def child1(vars):
            vars['count_enter'] += 1

            async with Nursery() as nursery:
                await sleep(0.1)
                await nursery.start_soon(child2(vars, 0.4))
                await nursery.start_soon(child2(vars, 0.1))

            vars['count_exit'] += 1

        async def child0():
            await sleep(0.4)
            raise Exception("STOP ALL")

        async def parent(vars):
            vars['count_enter'] = 0
            vars['count_exit'] = 0

            try:
                async with Nursery() as nursery:
                    await nursery.start_soon(child0())
                    await nursery.start_soon(child1(vars))
                    await sleep(0.1)
                    await nursery.start_soon(child1(vars))
            except Exception:
                pass

        for params in [
            ('FIFO', ),
            ('LIFO', )]:
            with self.subTest(execution_order=params[0]):
                vars = {}
                loop = Loop(execution_order=params[0])
                loop.start_soon(parent(vars))
                loop.run()
                self.assertEqual(vars['count_enter'], 6)
                self.assertEqual(vars['count_exit'], 2)

    def test_timeout(self):
        async def child2(vars, delay):
            vars['count_enter'] += 1
            await sleep(delay)
            vars['count_exit'] += 1

        async def child1(vars):
            vars['count_enter'] += 1

            async with Nursery() as nursery:
                await nursery.start_soon(child2(vars, 0.3))
                await nursery.start_soon(child2(vars, 0.1))

            vars['count_exit'] += 1

        async def parent(vars):
            vars['count_enter'] = 0
            vars['count_exit'] = 0

            try:
                async with Nursery(timeout=0.2) as nursery:
                    await nursery.start_soon(child1(vars))
            except Exception:
                pass

        for params in [
            ('FIFO', ),
            ('LIFO', )]:
            with self.subTest(execution_order=params[0]):
                vars = {}
                loop = Loop(execution_order=params[0])
                loop.start_soon(parent(vars))
                loop.run()
                self.assertEqual(vars['count_enter'], 3)
                self.assertEqual(vars['count_exit'], 1)


if __name__ == '__main__':
    main()
