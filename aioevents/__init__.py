import asyncio
import functools
import sys
import threading

from collections import defaultdict, abc

import aiorecycle

if (3, 5) <= sys.version_info < (3, 7):
    from typing import AsyncContextManager as AbstractAsyncContextManager
else:
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

from janus import Queue


__all__ = (
    "Event",

    "events",
    "manager",
    "worker",
)

__VERSION__ = "0.0.5"


@dataclass
class Event:
    pass


TEvent = Type[Event]


class _Manager:
    __slots__ = (
        '_events',
    )
    _handlers: DefaultDict[TEvent, List[Callable]] = defaultdict(list)

    def register(self, events: Union[TEvent, Sequence[TEvent]], **kwargs):
        self._events: Sequence[TEvent]

        if not isinstance(events, abc.Sequence):
            self._events = (events,)
        else:
            self._events = events

        def deco(func: Callable) -> Callable:
            for event in self._events:
                self._handlers[event].append(func)

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
            loop.run_until_complete(self.main())
            tasks = asyncio.all_tasks(loop)
            loop.run_until_complete(asyncio.gather(*tasks, loop=loop))
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            loop.close()

    def stop(self):
        self._stopped = True

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


    async def _handle_event(self, event: Event):
        manager = self._manager
        main_loop = self._main_loop

        for coro in manager.get(event):
            asyncio.run_coroutine_threadsafe(coro(event), main_loop)


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
