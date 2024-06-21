# Delete message notifier

## Install depends

```shell
pip3 install -r requirements.txt
```

## Usage

```plain
./notifier.py [<api id> <api hash> <upstream url> [listen group(s)]] [-h]
```

* You can obtain `api id` and `api hash` from [telegram](https://my.telegram.org/apps)
* Groups should separate by commas
* Upstream url support websocket and plain http (use POST method)
* Use `./notifier.py -h` to view more help messages.

## License

[![](https://www.gnu.org/graphics/agplv3-155x51.png)](https://www.gnu.org/licenses/agpl-3.0.txt)

Copyright (C) 2021-2024 KunoiSayami

This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License along with this program. If not, see <https://www.gnu.org/licenses/>.
