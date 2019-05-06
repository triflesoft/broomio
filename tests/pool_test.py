#!/usr/bin/env python3

from time import time
from time import sleep as time_sleep
from tracemalloc import start
from unittest import main
from unittest import TestCase
from broomio import Loop
from broomio import execute


start(4)


class TestPool(TestCase):
    def test_thread_pool(self):
        def handler(*args, **kwargs):
            time_sleep(0.5)
            return args[0] + args[1] + kwargs['c'] + kwargs['d']

        async def child(vars, index, a, b, c, d):
            vars[f'child_{index}_from'] = time()
            vars[f'child_{index}_data'] = await execute('test', a, b, c=c, d=d)
            vars[f'child_{index}_till'] = time()

        for params in [
            ('FIFO', 0.5, 1.0),
            ('LIFO', 1.0, 0.5)]:
            with self.subTest(execution_order=params[0]):
                vars = {}
                loop_from = time()
                loop = Loop(execution_order=params[0])
                loop.pool_init_thread('test', 2, lambda: handler)
                loop.start_soon(child(vars, 1, 1, 2, 3, 4))
                loop.start_soon(child(vars, 2, 2, 3, 4, 5))
                loop.start_soon(child(vars, 3, 3, 4, 5, 6))
                loop.start_soon(child(vars, 4, 4, 5, 6, 7))
                loop.run()
                loop_till = time()

                child_1_duration = vars['child_1_till'] - vars['child_1_from']
                child_2_duration = vars['child_2_till'] - vars['child_2_from']
                child_3_duration = vars['child_3_till'] - vars['child_3_from']
                child_4_duration = vars['child_4_till'] - vars['child_4_from']
                loop_duration = loop_till - loop_from

                self.assertAlmostEqual(child_1_duration, params[1], 1)
                self.assertAlmostEqual(child_2_duration, params[1], 1)
                self.assertAlmostEqual(child_3_duration, params[2], 1)
                self.assertAlmostEqual(child_4_duration, params[2], 1)
                self.assertAlmostEqual(loop_duration, 1.0, 0)

    def test_process_pool(self):
        def handler(*args, **kwargs):
            time_sleep(0.5)

            return args[0] + args[1] + kwargs['c'] + kwargs['d']

        async def child(vars, index, a, b, c, d):
            vars[f'child_{index}_from'] = time()
            vars[f'child_{index}_data'] = await execute('test', a, b, c=c, d=d)
            vars[f'child_{index}_till'] = time()

        for params in [
            ('FIFO', 0.5, 1.0),
            ('LIFO', 1.0, 0.5)]:
            with self.subTest(execution_order=params[0]):
                vars = {}
                loop_from = time()
                loop = Loop(execution_order=params[0])
                loop.pool_init_process('test', 2, lambda: handler)
                loop.start_soon(child(vars, 1, 1, 2, 3, 4))
                loop.start_soon(child(vars, 2, 2, 3, 4, 5))
                loop.start_soon(child(vars, 3, 3, 4, 5, 6))
                loop.start_soon(child(vars, 4, 4, 5, 6, 7))
                loop.run()
                loop_till = time()

                child_1_duration = vars['child_1_till'] - vars['child_1_from']
                child_2_duration = vars['child_2_till'] - vars['child_2_from']
                child_3_duration = vars['child_3_till'] - vars['child_3_from']
                child_4_duration = vars['child_4_till'] - vars['child_4_from']
                loop_duration = loop_till - loop_from

                self.assertAlmostEqual(child_1_duration, params[1], 1)
                self.assertAlmostEqual(child_2_duration, params[1], 1)
                self.assertAlmostEqual(child_3_duration, params[2], 1)
                self.assertAlmostEqual(child_4_duration, params[2], 1)
                self.assertAlmostEqual(loop_duration, 1.0, 0)


if __name__ == '__main__':
    main()

