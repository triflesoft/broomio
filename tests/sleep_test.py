#!/usr/bin/env python3

from time import time
from tracemalloc import start
from unittest import main
from unittest import TestCase
from broomio import Loop
from broomio import Nursery
from broomio import sleep


start(4)


class TestSleep(TestCase):
    def test_sleep_success(self):
        async def child(vars, index):
            vars[f'child_{index}_from'] = time()
            await sleep(2)
            vars[f'child_{index}_till'] = time()

        async def parent(vars):
            vars['parent_from'] = time()

            async with Nursery() as nursery:
                await nursery.start_soon(child(vars, 1))
                await nursery.start_later(child(vars, 2), 1)

            vars['parent_till'] = time()

        for params in [
            ('FIFO', ),
            ('LIFO', )]:
            with self.subTest(execution_order=params[0]):
                vars = {}
                loop = Loop(execution_order=params[0])
                loop.start_soon(parent(vars))
                loop.run()

                parent_duration  = vars['parent_till']  - vars['parent_from']
                child_1_offset   = vars['child_1_from'] - vars['parent_from']
                child_2_offset   = vars['child_2_from'] - vars['parent_from']
                child_1_duration = vars['child_1_till'] - vars['child_1_from']
                child_2_duration = vars['child_2_till'] - vars['child_2_from']

                self.assertAlmostEqual(parent_duration,  3.0, 1)
                self.assertAlmostEqual(child_1_offset,   0.0, 1)
                self.assertAlmostEqual(child_2_offset,   1.0, 1)
                self.assertAlmostEqual(child_1_duration, 2.0, 1)
                self.assertAlmostEqual(child_2_duration, 2.0, 1)

    def test_sleep_failure(self):
        async def child1(vars, index):
            try:
                vars[f'child_{index}_from'] = time()
                await sleep(2)
            finally:
                vars[f'child_{index}_till'] = time()

        async def child2(vars, index):
            try:
                vars[f'child_{index}_from'] = time()
                raise Exception('Test')
            finally:
                vars[f'child_{index}_till'] = time()

        async def parent(vars):
            try:
                vars['parent_from'] = time()

                async with Nursery() as nursery:
                    await nursery.start_soon(child1(vars, 1))
                    await nursery.start_later(child2(vars, 2), 1)
            except:
                pass
            finally:
                vars['parent_till'] = time()

        for params in [
            ('FIFO', ),
            ('LIFO', )]:
            with self.subTest(execution_order=params[0]):
                vars = {}
                loop = Loop(execution_order=params[0])
                loop.start_soon(parent(vars))
                loop.run()

                parent_duration  = vars['parent_till']  - vars['parent_from']
                child_1_offset   = vars['child_1_from'] - vars['parent_from']
                child_2_offset   = vars['child_2_from'] - vars['parent_from']
                child_1_duration = vars['child_1_till'] - vars['child_1_from']
                child_2_duration = vars['child_2_till'] - vars['child_2_from']

                self.assertAlmostEqual(parent_duration,  1.0, 1)
                self.assertAlmostEqual(child_1_offset,   0.0, 1)
                self.assertAlmostEqual(child_2_offset,   1.0, 1)
                self.assertAlmostEqual(child_1_duration, 1.0, 1)
                self.assertAlmostEqual(child_2_duration, 0.0, 1)


if __name__ == '__main__':
    main()

