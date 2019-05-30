import asyncio
import sys
import threading

from collections import defaultdict, abc

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

import janus


__all__ = (
    "Event",

    "events",
    "manager",
    "worker",
)

__VERSION__ = "0.0.3"


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
        if not isinstance(events, abc.Sequence):
            self._events: Sequence[TEvent] = (events,)
        else:
            self._events: Sequence[TEvent] = events

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
        '_main_loop',
        '_manager',
        '_stopped',
    )
    _loop = asyncio.new_event_loop()
    _queue: janus.Queue = janus.Queue(loop=_loop)

    def __init__(self, manager, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._manager = manager
        self._stopped = False
        self._main_loop = None

    @property
    def queue(self):
        return self._queue.async_q

    def run(self):
        self._loop.run_until_complete(self.main())

        self._loop.close()

    def stop(self):
        self._stopped = True

    def set_main_event_loop(self, loop):
        self._main_loop = loop

    def get_event_loop(self):
        return self._loop

    async def main(self):
        async_q = self._queue.async_q
        manager = self._manager
        main_loop = self._main_loop
        while not (self._stopped and async_q.empty()):
            try:
                event = async_q.get_nowait()
            except asyncio.QueueEmpty:
                pass
            else:
                coros = manager.get(event)
                for coro in coros:
                    asyncio.run_coroutine_threadsafe(
                        coro(event),
                        main_loop
                    )
                async_q.task_done()
            await asyncio.sleep(0.01)  # let other coroutines work


class _Events(AbstractAsyncContextManager):
    __slots__ = (
        '_queue',
    )

    _sleep = 0.001

    def __init__(self, worker, sleep: float = None):
        self._queue = worker.queue

        if sleep is not None:
            self._sleep = sleep

    async def publish(self, event: Event):
        future = asyncio.run_coroutine_threadsafe(
            self._queue.put(event),
            worker.get_event_loop()
        )
        future.result()  # wait for the event to be saved in the queue
        await asyncio.sleep(self._sleep)  # let other coroutines work

    async def __aexit__(self, *args, **kwargs):
        return None


manager = _Manager()
register = manager.register
worker = _Worker(manager)
events = _Events(worker)


def start(loop):
    worker.set_main_event_loop(loop)
    worker.start()


def stop():
    worker.stop()
    worker.join()
