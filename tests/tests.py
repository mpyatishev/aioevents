import asyncio

from concurrent.futures import Future

from unittest import mock

import pytest

import janus

from aioevents import (
    Event,

    _Manager,
    _Worker,
    _Events,
)


class QueueMock(janus.Queue):
    pass


class AsyncQueueMock:
    pass


@pytest.fixture
def loop():
    return asyncio.get_event_loop()


@pytest.fixture
def manager():
    manager = _Manager()
    yield manager
    manager.clear()


@pytest.fixture
def queue():
    mocked_queue = mock.MagicMock(spec=QueueMock)

    class async_q:
        _q = list()

        def put(self, e):
            self._q.append(e)

        def empty(self):
            return len(self._q) <= 0

        def get_nowait(self):
            try:
                return self._q[0]
            except IndexError:
                raise asyncio.QueueEmpty

        def task_done(self):
            try:
                del self._q[0]
            except IndexError:
                pass

    mocked_queue.async_q = async_q()

    return mocked_queue


@pytest.fixture
def worker(manager, loop, queue):
    worker = _Worker(manager)
    worker._queue = queue
    worker.set_main_event_loop(loop)
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
        assert manager._handlers[Event] == [handler]

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
        assert manager._handlers[Event] == [handler1, handler2]

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

        assert manager._handlers[Event] == [handler1]
        assert manager._handlers[OtherEvent] == [handler2]

    def test_get_should_return_list_of_handlers(self, manager):
        """
        it should return list of handlers
        """

        def handler(event):
            pass

        manager.register(Event)(handler)

        assert manager.get(Event) == [handler]
        assert manager.get(Event()) == [handler]


class TestWorker:
    @pytest.mark.asyncio
    async def test_should_call_handler_with_consumed_event_in_another_loop(
        self,
        loop,
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
        queue.put(Event)
        worker._stopped = True

        expected = [mock.call(None, loop)]

        with mock.patch('aioevents.asyncio.run_coroutine_threadsafe') as m_run:
            await worker.main()
            assert m_run.mock_calls == expected

    @pytest.mark.asyncio
    async def test_should_stop_on_signal(self, worker):
        """
        it should stop when the stop signal has been sent and queue is empty
        """

        worker.start()
        worker.stop()
        worker.join()

        assert not worker.is_alive()


class TestEvents:
    @pytest.mark.asyncio
    async def test_should_publish_event_to_queue(self, events, worker):
        """
        it should publish event to the queue
        """

        expected = [mock.call(None, worker._loop)]
        future = Future()
        future.set_result(None)

        with mock.patch('aioevents.asyncio.run_coroutine_threadsafe') as m_run:
            m_run.return_value = future

            await events.publish(Event)

            assert m_run.mock_calls == expected

        assert not worker.queue.empty()
        assert worker.queue.get_nowait() == Event
