import asyncio
import logging
import threading

from collections import defaultdict, abc
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from functools import wraps
from typing import (
    Callable,
    DefaultDict,
    List,
    Optional,
    Sequence,
    Type,
    Union,
)

import aiorecycle

from janus import Queue


__all__ = (
    "Event",

    "events",
    "manager",
    "worker",
)

__VERSION__ = "0.0.7"


logger = logging.getLogger(__name__)


@dataclass
class Event:
    pass


TEvent = Type[Event]


class _Task:
    def __init__(self, func, retry=None, *args, **kwargs):
        self._retries = retry
        self._func = func

    def can_retry(self):
        return self._retries and self._retries > 0

    def __call__(self, event):
        if self._retries:
            self._retries -= 1
        return self._func(event)


class _Manager:
    __slots__ = (
        '_events',
    )
    _handlers: DefaultDict[TEvent, List[Callable]] = defaultdict(list)

    def register(
        self,
        events: Union[TEvent, Sequence[TEvent]],
        retry: Optional[int] = None,
        **kwargs
    ):
        self._events: Sequence[TEvent]

        if not isinstance(events, abc.Sequence):
            self._events = (events,)
        else:
            self._events = events

        def deco(func: Callable) -> Callable:
            task = _Task(func, retry)
            for event in self._events:
                self._handlers[event].append(task)

            @wraps(func)
            def wrapper(*fargs, **fkwargs) -> Callable:
                return func(*fargs, **fkwargs)

            return wrapper

        return deco

    def clear(self, events: Optional[Union[TEvent, Sequence[TEvent]]] = None):
        _events: Sequence[TEvent] = tuple()

        if events is None:
            _events = tuple(self._handlers.keys())
        elif not isinstance(events, abc.Sequence):
            _events = (events,)
        else:
            _events = events

        for event in _events:
            del self._handlers[event]

    def get(self, event: Event) -> List[Callable]:
        if not isinstance(event, type):
            return self._handlers[event.__class__]
        return self._handlers[event]


class _Worker(threading.Thread):
    __slots__ = (
        '_loop',
        '_main_loop',
        '_manager',
        '_queue',
        '_stopped',
        '_retry_queue',
    )

    def __init__(
        self,
        manager: _Manager,
        queue: Queue,
        loop: asyncio.AbstractEventLoop,
        *args, **kwargs
    ):
        super().__init__(*args, **kwargs)

        self._loop = loop
        self._queue = queue
        self._manager = manager
        self._stopped = False
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        self._retry_queue: list = list()

    @property
    def queue(self):
        return self._queue.async_q

    @property
    def loop(self):
        return self._loop

    def run(self):
        if self._main_loop is None:
            raise Exception('main loop is not set')

        loop = self._loop
        try:
            loop.create_task(self._do_retries())
            loop.create_task(self.main())
            loop.run_forever()
        finally:
            tasks = asyncio.all_tasks(loop)
            loop.run_until_complete(asyncio.gather(*tasks, loop=loop))
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

    def stop(self):
        self._stopped = True
        self.loop.stop()

    def set_main_event_loop(self, loop: asyncio.AbstractEventLoop):
        self._main_loop = loop

    @aiorecycle.cycle(sleep=0.01)
    async def main(self):
        async_q = self._queue.async_q
        if (self._stopped and async_q.empty()):
            raise aiorecycle.CycleStop()

        try:
            event = async_q.get_nowait()
        except asyncio.QueueEmpty:
            pass
        else:
            await self._handle_event(event)
            async_q.task_done()

    @aiorecycle.cycle(sleep=0.1)
    async def _do_retries(self):
        if self._stopped and not self._retry_queue:
            raise aiorecycle.CycleStop()
        elif self._retry_queue:
            event, task = self._retry_queue.pop()
            await self._do(task, event)

    async def _do(
        self,
        task: Callable,
        event: Event
    ):
        def future_done(future):
            try:
                future.result()
            except Exception as e:
                logger.exception(e)
                if task.can_retry():
                    self._retry_queue.append((event, task))

        try:
            future = asyncio.run_coroutine_threadsafe(
                task(event),
                self._main_loop
            )
            future.add_done_callback(future_done)
        except Exception as e:
            logger.exception(e)

    async def _handle_event(self, event: Event):
        manager = self._manager

        for task in manager.get(event):
            await self._do(task, event)


class _Events(AbstractAsyncContextManager):
    __slots__ = (
        '_queue',
        '_loop',
    )

    def __init__(self, worker: _Worker):
        self._queue = worker.queue
        self._loop = worker.loop

    async def publish(self, event: Event):
        future = asyncio.run_coroutine_threadsafe(
            self._queue.put(event),
            self._loop,
        )
        future.result()

    async def __aexit__(self, *args, **kwargs):
        return None


manager = _Manager()
register = manager.register
loop = asyncio.new_event_loop()
queue: Queue = Queue(loop=loop)
worker = _Worker(manager, queue, loop)
events = _Events(worker)


def start(loop: asyncio.AbstractEventLoop):
    worker.set_main_event_loop(loop)
    worker.start()


def stop():
    worker.stop()
    worker.join()
