import asyncio
import threading

from collections import defaultdict, abc
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from functools import wraps
from typing import DefaultDict, Callable, List, Sequence, Type, Union

import janus


__all__ = (
    "Event",

    "events",
    "manager",
    "worker",
)

__VERSION__ = "0.0.1"


@dataclass
class Event:
    pass


TEvent = Type[Event]


class _Manager:
    handlers: DefaultDict[TEvent, List[Callable]] = defaultdict(list)

    def register(self, events: Union[TEvent, Sequence[TEvent]], **kwargs):
        if not isinstance(events, abc.Sequence):
            self._events: Sequence[TEvent] = (events,)
        else:
            self._events: Sequence[TEvent] = events

        def deco(func: Callable) -> Callable:
            for event in self._events:
                self.handlers[event].append(func)

            @wraps(func)
            def wrapper(*fargs, **fkwargs) -> Callable:
                return func(*fargs, **fkwargs)

            return wrapper

        return deco

    def get(self, event: Event) -> List[Callable]:
        if not isinstance(event, type):
            return self.handlers[event.__class__]
        return self.handlers[event]


class _Worker(threading.Thread):
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
            await asyncio.sleep(0.001)  # let other coroutine work


class _Events(AbstractAsyncContextManager):
    def __init__(self):
        self._queue = worker.queue

    async def publish(self, event: Event):
        asyncio.run_coroutine_threadsafe(
            self._queue.put(event),
            worker.get_event_loop()
        )

    async def __aexit__(self, *args, **kwargs):
        return None


manager = _Manager()
register = manager.register
worker = _Worker(manager)
events = _Events()
