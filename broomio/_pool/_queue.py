from multiprocessing import Process

try:
    from multiprocessing import SimpleQueue as ProcessQueue
except ImportError:
    from multiprocessing import Queue as ProcessQueue

try:
    from queue import SimpleQueue as ThreadQueue
except ImportError:
    from queue import Queue as ThreadQueue

from threading import Thread
from time import sleep
from .._util import _LoopSlots


class ThreadPoolTask:
    __slots__ = 'loop', 'task_info', 'args', 'kwargs'

    def __init__(self, loop, task_info, args, kwargs):
        self.loop = loop
        self.task_info = task_info
        self.args = args
        self.kwargs = kwargs


class ThreadPool:
    __slots__ = 'loop', 'task_handler_factory', 'threads', 'request_queue'

    def _thread_worker(self):
        task_handler = self.task_handler_factory()

        while True:
            task = self.request_queue.get()

            if task is None:
                break

            task_info = task.task_info
            task_info.send_args = task_handler(*task.args, **task.kwargs)
            self.loop._task_enqueue_one(task_info)
            self.loop._pool_task_count -= 1

    def __init__(self, loop, task_handler_factory, thread_number):
        self.loop = loop
        self.task_handler_factory = task_handler_factory
        self.threads = []
        self.request_queue = ThreadQueue()

        for _ in range(thread_number):
            thread = Thread(target=self._thread_worker)
            thread.start()
            self.threads.append(thread)

    def enqueue(self, task_info, args, kwargs):
        self.request_queue.put(ThreadPoolTask(self.loop, task_info, args, kwargs))

    def terminate(self):
        for _ in range(len(self.threads)):
            self.request_queue.put(None)


class ProcessPoolRequest:
    __slots__ = 'task_info_id', 'args', 'kwargs'

    def __init__(self, task_info_id, args, kwargs):
        self.task_info_id = task_info_id
        self.args = args
        self.kwargs = kwargs


class ProcessPoolResponce:
    __slots__ = 'task_info_id', 'send_args', 'throw_exc'

    def __init__(self, task_info_id, send_args, throw_exc):
        self.task_info_id = task_info_id
        self.send_args = send_args
        self.throw_exc = throw_exc


def _process_pool_process_worker(request_queue, response_queue, task_handler_factory):
    task_handler = task_handler_factory()

    while True:
        request = request_queue.get()

        if request is None:
            break

        try:
            send_args = task_handler(*request.args, **request.kwargs)
            response_queue.put(ProcessPoolResponce(request.task_info_id, send_args, None))
        except BaseException as throw_exc:
            response_queue.put(ProcessPoolResponce(request.task_info_id, None, throw_exc))


class ProcessPool:
    __slots__ = 'loop', 'task_handler_factory', 'thread', 'processes', 'request_queue', 'response_queue', 'task_info_map'

    def _thread_worker(self):
        while True:
            response = self.response_queue.get()

            if response is None:
                break

            task_info = self.task_info_map[response.task_info_id]
            task_info.send_args = response.send_args
            task_info.throw_exc = response.throw_exc
            self.loop._task_enqueue_one(task_info)
            self.loop._pool_task_count -= 1

    def __init__(self, loop, task_handler_factory, thread_number):
        self.loop = loop
        self.task_handler_factory = task_handler_factory
        self.thread = Thread(target=self._thread_worker)
        self.processes = []
        self.request_queue = ProcessQueue()
        self.response_queue = ProcessQueue()
        self.task_info_map = {}

        for _ in range(thread_number):
            process = Process(target=_process_pool_process_worker, args=(self.request_queue, self.response_queue, self.task_handler_factory))
            process.start()
            self.processes.append(process)

        self.thread.start()

    def enqueue(self, task_info, args, kwargs):
        self.task_info_map[id(task_info)] = task_info
        self.request_queue.put(ProcessPoolRequest(id(task_info), args, kwargs))

    def terminate(self):
        for _ in range(len(self.processes)):
            self.request_queue.put(None)

        self.response_queue.put(None)


class LoopPoolQueue(_LoopSlots):
    def pool_init_thread(self, name, thread_number, task_handler_factory):
        self._pool_queue_map[name] = ThreadPool(self, task_handler_factory, thread_number)

    def pool_init_process(self, name, process_number, task_handler_factory):
        self._pool_queue_map[name] = ProcessPool(self, task_handler_factory, process_number)

    def _pool_term_all(self):
        for pool_queue in self._pool_queue_map.values():
            pool_queue.terminate()

    def _pool_enqueue(self, _name, _task_info, args, kwargs):
        self._pool_queue_map[_name].enqueue(_task_info, args, kwargs)
        self._pool_task_count += 1

    def _process_pool(self):
        if not self._task_deque:
            # FIXME: Maybe anything better?
            sleep(0.001)
