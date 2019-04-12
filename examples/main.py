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


async def one():
    async with aioevents.events as events:
        for i in range(10):
            await events.publish(SimpleEvent(str(i)))
            await asyncio.sleep(random.random())
        await events.publish(SimpleEvent("last payload from one"))


async def two():
    async with aioevents.events as events:
        for i in range(10, 20):
            await events.publish(SimpleEvent(str(i)))
            await asyncio.sleep(random.random())
        await events.publish(SimpleEvent("last payload from two"))


async def main():
    aioevents.start(asyncio.get_event_loop())

    await asyncio.gather(one(), two())

    aioevents.stop()

    # wait for all coroutines
    await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
