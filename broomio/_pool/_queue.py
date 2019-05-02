from multiprocessing import Process
from multiprocessing import Queue
from queue import SimpleQueue
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
    __slots__ = 'loop', 'task_handler', 'threads', 'request_queue'

    def _thread_worker(self):
        while True:
            task = self.request_queue.get()

            if task is None:
                break

            task_info = task.task_info
            task_info.send_args = self.task_handler(*task.args, **task.kwargs)
            self.loop._task_enqueue_one(task_info)
            self.loop._pool_task_count -= 1

    def __init__(self, loop, task_handler, thread_number):
        self.loop = loop
        self.task_handler = task_handler
        self.threads = []
        self.request_queue = SimpleQueue()

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
    def __init__(self, task_info_id, args, kwargs):
        self.task_info_id = task_info_id
        self.args = args
        self.kwargs = kwargs


class ProcessPoolResponce:
    def __init__(self, task_info_id, result):
        self.task_info_id = task_info_id
        self.result = result


def _process_pool_process_worker(request_queue, response_queue, task_handler):
    while True:
        request = request_queue.get()

        if request is None:
            break

        # TODO: Process exceptions.
        result = task_handler(*request.args, **request.kwargs)

        response_queue.put(ProcessPoolResponce(request.task_info_id, result))


class ProcessPool:
    __slots__ = 'loop', 'task_handler', 'thread', 'processes', 'request_queue', 'response_queue', 'task_info_map'

    def _thread_worker(self):
        while True:
            response = self.response_queue.get()

            if response is None:
                break

            task_info = self.task_info_map[response.task_info_id]
            task_info.send_args = response.result
            self.loop._task_enqueue_one(task_info)
            self.loop._pool_task_count -= 1

    def __init__(self, loop, task_handler, thread_number):
        self.loop = loop
        self.task_handler = task_handler
        self.thread = Thread(target=self._thread_worker)
        self.processes = []
        self.request_queue = Queue()
        self.response_queue = Queue()
        self.task_info_map = {}

        for _ in range(thread_number):
            process = Process(target=_process_pool_process_worker, args=(self.request_queue, self.response_queue, self.task_handler))
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
    def pool_init_thread(self, name, thread_number, task_handler):
        self._pool_queue_map[name] = ThreadPool(self, task_handler, thread_number)

    def pool_init_process(self, name, process_number, task_handler):
        self._pool_queue_map[name] = ProcessPool(self, task_handler, process_number)

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
