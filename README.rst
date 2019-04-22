Broomio
=======

History
-------

Why one more async library? Broomio started as an experiment. This code meant to be thrown away. I was inspired by curio and trio libraries, code looked so clean and easy to understand. That was brave new Python, which is easy to understand. Curio is the first challenger, questioning existing standard library choices; and Trio is the place where real science happens. Also authors of both libraries are really friendly, thank you `David Beazley <https://github.com/dabeaz/>`_ and `Nathaniel J. Smith <https://github.com/njsmith>`_! However, I was curios what are Python asyncio limits? Can asyncio based network server written in beautiful clean manner be as performant as raw epoll based with ugly spagetti callbacks? It turns out the answer is yes, but not without some tradeoffs.

Getting Started
---------------

Installation
""""""""""""

Broomio can be installed with pip.

::

    pip3 install broomio

Usage
""""""""""""

First of all, you'll need a loop. Loops are common concept in async libraries. Broomio provides no default loop, so loop should be created and started explicitly.

::

    from broomio import Loop

    loop = Loop()
    loop.run()

However this loop has nothing to do and will exit immediately. Lets add some coroutine and execute it a few times. Read more about coroutines in `PEP 0492 <https://www.python.org/dev/peps/pep-0492/>`_.

::

    from broomio import Loop
    from broomio import sleep
    from time import time

    async def test(index):
        print(f'{index} started at {time()}')
        await sleep(2)
        print(f'{index} stopped at {time()}')


    loop = Loop()
    loop.start_soon(test(1))
    loop.start_soon(test(2))
    loop.start_soon(test(3))
    loop.run()


You will see output like the following

::

    3 started at 1456789015.0144565
    2 started at 1456789015.0147984
    1 started at 1456789015.0149508
    3 stopped at 1456789017.0166693
    2 stopped at 1456789017.0171447
    1 stopped at 1456789017.0180902


The first thing to notice is that some functions which pause or block execution, like sleep, should be called with await. Skipping await will lead to all kinds of unexpected bad consequences. So be careful.
The second thing to notice is that coroutines behave more or less like threads. Please, find bellow equivalent code with threads.

::

    from threading import Thread
    from time import sleep
    from time import time

    def test(index):
        print(f'{index} started at {time()}')
        sleep(2)
        print(f'{index} stopped at {time()}')

    t1 = Thread(target=lambda: child(1))
    t2 = Thread(target=lambda: child(2))
    t3 = Thread(target=lambda: child(3))

    t1.start()
    t2.start()
    t3.start()
    t1.join()
    t2.join()
    t3.join()

Output will be similar

::

    1 started at 1456789015.0149508
    3 started at 1456789015.0144565
    2 started at 1456789015.0147984
    1 stopped at 1456789017.0180902
    2 stopped at 1456789017.0171447
    3 stopped at 1456789017.0166693

Difference is that coroutines actually work in context of single thread. There are no operating system level threads or anything similar, it's pure user code solution. Kernel is not aware of coroutines.

Find more examples in `corresponding folder <examples>`_ in source code.
