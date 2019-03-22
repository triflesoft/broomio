from broomio import Loop
from broomio import Nursery
from broomio import sleep
from math import fabs
from time import time
from unittest import main
from unittest import TestCase


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

        vars = {}
        loop = Loop()
        loop.start_soon(parent(vars))
        loop.run()

        parent_duration  = fabs(vars['parent_till']  - vars['parent_from'] )
        child_1_offset   = fabs(vars['child_1_from'] - vars['parent_from'] )
        child_2_offset   = fabs(vars['child_2_from'] - vars['parent_from'] )
        child_1_duration = fabs(vars['child_1_till'] - vars['child_1_from'])
        child_2_duration = fabs(vars['child_2_till'] - vars['child_2_from'])

        self.assertAlmostEqual(parent_duration,  3.0, 2)
        self.assertAlmostEqual(child_1_offset,   0.0, 2)
        self.assertAlmostEqual(child_2_offset,   1.0, 2)
        self.assertAlmostEqual(child_1_duration, 2.0, 2)
        self.assertAlmostEqual(child_2_duration, 2.0, 2)

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
                pass
            finally:
                vars['parent_till'] = time()

        vars = {}
        loop = Loop()
        loop.start_soon(parent(vars))
        loop.run()

        parent_duration  = fabs(vars['parent_till']  - vars['parent_from'] )
        child_1_offset   = fabs(vars['child_1_from'] - vars['parent_from'] )
        child_2_offset   = fabs(vars['child_2_from'] - vars['parent_from'] )
        child_1_duration = fabs(vars['child_1_till'] - vars['child_1_from'])
        child_2_duration = fabs(vars['child_2_till'] - vars['child_2_from'])

        self.assertAlmostEqual(parent_duration,  1.0, 2)
        self.assertAlmostEqual(child_1_offset,   0.0, 2)
        self.assertAlmostEqual(child_2_offset,   1.0, 2)
        self.assertAlmostEqual(child_1_duration, 1.0, 2)
        self.assertAlmostEqual(child_2_duration, 0.0, 2)


if __name__ == '__main__':
    main()

