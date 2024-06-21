#!/usr/bin/env python3
# Copyright (C) 2021 KunoiSayami and contributors
#
# This module is part of delete-message-notifier and is released under
# the AGPL v3 License: https://www.gnu.org/licenses/agpl-3.0.txt
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
from __future__ import annotations

import ast
import argparse
import asyncio
import json
import logging
import sys

from abc import ABCMeta, abstractmethod
from typing import Sequence

import aiohttp
import pyrogram
from pyrogram import Client, filters
from pyrogram.handlers import DeletedMessagesHandler
from pyrogram.types import Message


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
        self.connection: aiohttp.ClientWebSocketResponse | None = None

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
                 target_group: int | Sequence[int] | None,
                 upstream: UpstreamManager):
        self.app = Client(session_name, api_id, api_hash)
        if isinstance(target_group, int):
            self.target_group = [target_group]
        else:
            self.target_group = target_group
        self.upstream = upstream
        self.app.add_handler(DeletedMessagesHandler(self.deleted_message_handler, filters.channel | filters.group))
        self.logger = logging.getLogger('ApiClient')
        self.logger.setLevel(logging.DEBUG)

    @classmethod
    async def create(cls,
                     session_name: str,
                     api_id: int,
                     api_hash: str,
                     target_group: int | Sequence[int] | None,
                     upstream_url: str) -> ApiClient:
        if upstream_url.startswith('ws'):
            upstream = WebsocketUpstreamManager.create(upstream_url)
        else:
            upstream = PlainHttpUpstreamManager.create(upstream_url)
        return cls(session_name, api_id, api_hash, target_group, await upstream)

    async def deleted_message_handler(self, _: Client, messages: Sequence[Message]) -> None:
        chat_id = messages[0].chat.id
        if self.target_group is None or chat_id in self.target_group:
            await self.upstream.send(json.dumps(dict(id=chat_id, delete_messages=[m.message_id for m in messages])))

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


async def main(args: argparse.Namespace):
    client = await ApiClient.create(
        'notifier', args.api_id, args.api_hash,
        None if args.groups == 'any' else ast.literal_eval(args.groups),
        args.upstream)
    await client.start()
    await pyrogram.idle()
    await client.stop()
    await client.cleanup()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog=sys.argv[0])
    parser.add_argument('api_id', help='Telegram App api_id', type=int)
    parser.add_argument('api_hash', help='Telegram App api hash')
    parser.add_argument('upstream', help='Upstream url, support websocket and HTTP POST')
    parser.add_argument('groups', nargs='?', default='any',
                        help='Listen to group(s), groups should separate by commas. '
                             'Or simply leave blank to listen all groups.')
    args_ = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s - %(levelname)s - %(name)s - %(funcName)s - %(lineno)d - %(message)s')
    logging.getLogger('pyrogram').setLevel(logging.WARNING)
    asyncio.run(main(args_))
