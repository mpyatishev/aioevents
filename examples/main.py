import asyncio
import random

from dataclasses import dataclass

import aioevents


@dataclass
class SimpleEvent(aioevents.Event):
    payload: str


@aioevents.manager.register(SimpleEvent)
async def event_hadler(event: aioevents.Event):
    print(f"recieved: {event}")


events_num = 2


async def one():
    async with aioevents.events as events:
        for i in range(events_num):
            event = SimpleEvent(str(i))
            print(f'sending: {event}')
            await events.publish(event)
            # await asyncio.sleep(random.random())
        await events.publish(SimpleEvent("last payload from one"))


async def two():
    async with aioevents.events as events:
        for i in range(events_num, events_num * 2):
            event = SimpleEvent(str(i))
            print(f'sending: {event}')
            await events.publish(event)
            # await asyncio.sleep(random.random())
        await events.publish(SimpleEvent("last payload from two"))


async def main():
    loop = asyncio.get_event_loop()
    aioevents.start(loop)

    await asyncio.gather(one(), two())

    await asyncio.sleep(10)
    print('stopping worker')
    aioevents.stop()

    # wait for all coroutines
    await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
