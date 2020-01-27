import asyncio

from unittest import mock

import pytest

import janus

from aioevents import (
    Event,

    _Events,
    _Manager,
    _Task,
    _Worker,
)


@pytest.fixture
def manager():
    manager = _Manager()
    yield manager
    manager.clear()


@pytest.fixture
def new_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.stop()
    loop.close()


@pytest.fixture
def queue(new_loop):
    return asyncio.Queue(loop=new_loop)


@pytest.fixture
def worker(manager, event_loop, new_loop, queue):
    worker = _Worker(manager, queue, new_loop)
    worker.set_main_event_loop(event_loop)
    yield worker


@pytest.fixture
def events(worker):
    return _Events(worker)


class TestManager:
    def test_register_should_bind_event_to_handler(self, manager):
        """
        it should bind event to handler
        """

        def handler(event):
            pass

        manager.register(Event)(handler)

        assert Event in manager._handlers

        task = manager._handlers[Event][0]
        assert isinstance(task, _Task)
        assert task._func == handler

    def test_register_should_bind_events_to_handler(self, manager):
        """
        it should bind collection of events to handler
        """

        def handler1(event):
            pass

        def handler2(event):
            pass

        manager.register(Event)(handler1)
        manager.register(Event)(handler2)

        assert Event in manager._handlers
        for elem in manager._handlers[Event]:
            assert isinstance(elem, _Task)
        for task, handler in zip(
            manager._handlers[Event],
            [handler1, handler2]
        ):
            assert task._func == handler

    def test_register_with_different_events(self, manager):
        """
        it should bind different events to different handlers
        """

        def handler1(event):
            pass

        def handler2(event):
            pass

        class OtherEvent(Event):
            pass

        manager.register(Event)(handler1)
        manager.register(OtherEvent)(handler2)

        assert Event in manager._handlers
        assert OtherEvent in manager._handlers

        task = manager._handlers[Event][0]
        assert isinstance(task, _Task)
        assert task._func == handler1

        task = manager._handlers[OtherEvent][0]
        assert isinstance(task, _Task)
        assert task._func == handler2

    def test_get_should_return_list_of_handlers(self, manager):
        """
        it should return list of handlers
        """

        def handler(event):
            pass

        manager.register(Event)(handler)

        task = manager.get(Event)[0]
        assert isinstance(task, _Task)
        assert task._func == handler

        task = manager.get(Event())[0]
        assert isinstance(task, _Task)
        assert task._func == handler


class TestWorker:
    @pytest.mark.asyncio
    async def test_should_call_handler_with_consumed_event_in_another_loop(
        self,
        event_loop,
        manager,
        worker,
        events,
    ):
        """
        it should call handler with consumed event in another event-loop
        """

        @manager.register(Event)
        def handler(event):
            pass

        queue = worker.queue
        await queue.put(Event)

        expected = [mock.call(None, event_loop)]

        with mock.patch('aioevents.asyncio.run_coroutine_threadsafe') as m_run:
            worker.start()
            worker.stop()
            worker.join()
            assert expected in m_run.mock_calls

    @pytest.mark.asyncio
    async def test_should_stop_on_signal(self, worker):
        """
        it should stop when the stop signal has been sent and queue is empty
        """

        worker.start()
        worker.stop()
        worker.join()

        assert not worker.is_alive()

    @pytest.mark.asyncio
    async def test_should_reenqueue_coro_on_exception(
        self,
        manager,
        worker,
        events,
    ):
        """
        it should reenqueue the coroutine in case of exception other than CancelledError
        """  # noqa

        @manager.register(Event, retry=3)
        async def handler(event):
            raise Exception("some exception here")

        queue = worker.queue
        await queue.put(Event)

        worker.start()
        worker.stop()
        worker.join()

        await asyncio.sleep(0.001)  # let coro do its work

        assert queue.empty()
        assert (Event, worker._manager.get(Event)[0]) in worker._retry_queue

    @pytest.mark.asyncio
    async def test_should_do_retries(
        self,
        manager,
        worker,
        events,
    ):
        """
        it should process the list of retries
        """

        count = 1

        @manager.register(Event, retry=3)
        async def handler(event):
            nonlocal count
            count += 1
            raise Exception("some exception here")

        task = worker._manager.get(Event)[0]
        initial_retries = task._retries

        worker._retry_queue.append((Event, task))
        worker._stopped = True

        await worker._do_retries()

        curr = asyncio.current_task()
        tasks = asyncio.all_tasks() - {curr}
        await asyncio.gather(*tasks)

        assert task._retries < initial_retries
        assert count == 3


class TestEvents:
    @pytest.mark.asyncio
    async def test_should_publish_event_to_queue(self, events, worker):
        """
        it should publish event to the queue
        """

        async def main():
            pass

        with mock.patch.object(worker, 'main') as m_main:
            m_main.side_effect = main
            worker.start()
            await events.publish(Event)
            worker.stop()
            worker.join()

        assert not worker.queue.empty()
        assert worker.queue.get_nowait() == Event
