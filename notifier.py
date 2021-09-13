#!/usr/bin/env python3
from __future__ import annotations

import ast
import asyncio
import json
import logging
import sys

from abc import ABCMeta, abstractmethod
from typing import Union, Sequence, Optional

import aiohttp
import pyrogram
from pyrogram import Client
from pyrogram.types import Update
from pyrogram.handlers import RawUpdateHandler


class UpstreamManager(metaclass=ABCMeta):
    def __init__(self, upstream_url: str, session: aiohttp.ClientSession):
        self.upstream_url = upstream_url
        self.session = session
        self.logger = logging.getLogger('UpstreamManager')
        self.logger.setLevel(logging.INFO)

    @classmethod
    async def create(cls, upstream_url: str) -> UpstreamManager:
        session = aiohttp.ClientSession()
        return cls(upstream_url, session)

    async def connect(self, *, force: bool = False) -> None:
        pass

    @abstractmethod
    async def send(self, data: str) -> None:
        raise NotImplementedError

    async def disconnect(self) -> None:
        pass

    async def cleanup(self) -> None:
        await self.session.close()
        self.session = None


class WebsocketUpstreamManager(UpstreamManager):
    def __init__(self, upstream_url: str, session: aiohttp.ClientSession):
        super().__init__(upstream_url, session)
        self.connection: Optional[aiohttp.ClientWebSocketResponse] = None

    async def send(self, data: str) -> None:
        for retries in range(1, 5):
            try:
                await self.connection.send_str(data)
                break
            except (ConnectionResetError, ConnectionAbortedError):
                self.logger.exception('Got exception while send message')
                await self.connect(force=True)
                if retries > 3:
                    raise
        self.logger.debug('Send %s successful', data)

    async def connect(self, *, force: bool = False) -> None:
        if not force and self.connection is not None:
            return
        if self.connection:
            try:
                await self.connection.close()
            except ConnectionResetError:
                self.logger.exception('Got ConnectionError while close connection')
        self.connection = await self.session.ws_connect(self.upstream_url)

    async def disconnect(self) -> None:
        if self.connection is None:
            return
        try:
            await self.connection.close()
        except ConnectionResetError:
            pass
        self.connection = None


class PlainHttpUpstreamManager(UpstreamManager):

    async def send(self, data: str) -> None:
        await self.session.post(self.upstream_url, data=data, headers={'content-type': 'application/json'})


class ApiClient:
    def __init__(self,
                 session_name: str,
                 api_id: int,
                 api_hash: str,
                 target_group: Union[int, Sequence[int]],
                 upstream: UpstreamManager):
        self.app = Client(session_name, api_id, api_hash)
        if isinstance(target_group, int):
            self.target_group = [target_group]
        else:
            self.target_group = target_group
        self.upstream = upstream
        self.app.add_handler(RawUpdateHandler(self.raw_handler))
        self.logger = logging.getLogger('ApiClient')
        self.logger.setLevel(logging.DEBUG)

    @classmethod
    async def create(cls,
                     session_name: str,
                     api_id: int,
                     api_hash: str,
                     target_group: Union[int, Sequence[int]],
                     upstream_url: str) -> ApiClient:
        if upstream_url.startswith('ws'):
            upstream = WebsocketUpstreamManager.create(upstream_url)
        else:
            upstream = PlainHttpUpstreamManager.create(upstream_url)
        return cls(session_name, api_id, api_hash, target_group, await upstream)

    async def raw_handler(self, _client: Client, update: Update, _users: dict, _chats: dict) -> None:
        if isinstance(update, pyrogram.raw.types.UpdateDeleteChannelMessages):
            if (group_id := -(update.channel_id + 1000000000000)) in self.target_group:
                await self.upstream.send(json.dumps(dict(id=group_id, delete_messages=update.messages)))

    async def start(self) -> None:
        await self.upstream.connect()
        await self.app.start()

    async def stop(self) -> None:
        await self.app.stop()
        await self.upstream.disconnect()

    async def cleanup(self) -> None:
        await self.upstream.cleanup()

    @staticmethod
    async def idle() -> None:
        await pyrogram.idle()


async def main():
    client = await ApiClient.create(
        'notifier', int(sys.argv[1]), sys.argv[2], ast.literal_eval(sys.argv[3]), sys.argv[4])
    await client.start()
    await client.idle()
    await client.stop()
    await client.cleanup()

if __name__ == '__main__':
    if len(sys.argv) < 5:
        print('Usage:', sys.argv[0], '<api id> <api hash> <listen group(s)> <upstream url>', file=sys.stderr)
        raise SystemExit
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s - %(levelname)s - %(name)s - %(funcName)s - %(lineno)d - %(message)s')
    logging.getLogger('pyrogram').setLevel(logging.WARNING)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
