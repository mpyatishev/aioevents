=========
aioevents
=========
.. image:: https://travis-ci.com/mpyatishev/aioevents.svg?branch=master
    :target: https://travis-ci.com/mpyatishev/aioevents
.. image:: https://codecov.io/gh/mpyatishev/aioevents/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/mpyatishev/aioevents
.. image:: https://img.shields.io/pypi/v/aioevents.svg
    :target: https://pypi.python.org/pypi/aioevents


A simple library for managing events through an asynchronous queue


Installation
============

.. code:: bash

   pip install aioevents

`Note`: for python 3.6 you need to install ``dataclasses``

.. code:: bash

   pip install dataclasses


Usage example
=============

.. code:: python

   import asyncio

   from dataclasses import dataclass

   import aioevents


   @dataclass
   class MyEvent(aioevents.Event):
      payload: str


   @aioevents.manager.register(MyEvent)
   async def event_hadler(event: aioevents.Event):
      print(f"recieved: {event}")


   async def produce():
      async with aioevents.events as events:
         await events.publish(MyEvent("Hello!"))


   async def main():
      aioevents.start(asyncio.get_event_loop())

      await produce()

      print('stopping worker')
      aioevents.stop()

      # wait for all coroutines
      await asyncio.sleep(1)


   if __name__ == "__main__":
      asyncio.run(main())


License
=======
``aioevents`` library is offered under Apache 2 license.
