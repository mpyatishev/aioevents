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


events_num = 200


async def one():
    async with aioevents.events as events:
        for i in range(events_num):
            await asyncio.sleep(random.random())  # emulate some work
            event = SimpleEvent(str(i))
            print(f'sending: {event}')
            await events.publish(event)
        await events.publish(SimpleEvent("last payload from one"))


async def two():
    async with aioevents.events as events:
        for i in range(events_num, events_num * 2):
            await asyncio.sleep(random.random())  # emulate some work
            event = SimpleEvent(str(i))
            print(f'sending: {event}')
            await events.publish(event)
        await events.publish(SimpleEvent("last payload from two"))


async def main():
    loop = asyncio.get_event_loop()
    aioevents.start(loop)

    await asyncio.gather(one(), two())

    print('stopping worker')
    aioevents.stop()

    print('wait all tasks done')
    # switch context to let other tasks done
    await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
