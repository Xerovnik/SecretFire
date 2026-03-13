# GhostWire
# Copyright (C) 2026 J. Zerovnik
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import os
from pathlib import Path

APP_NAME = "GhostWire"
APP_VERSION = "0.1.0"

DATA_DIR = Path.home() / ".ghostwire"
DB_PATH = DATA_DIR / "node.db"
TOR_DATA_DIR = DATA_DIR / "tor_data"
TOR_HIDDEN_SERVICE_DIR = DATA_DIR / "hidden_service"
KEY_FILE = DATA_DIR / "node_keys.json"

FLASK_PORT = int(os.environ.get("PORT", 7474))
FLASK_HOST = "127.0.0.1"

TOR_SOCKS_PORT = 9150
TOR_CONTROL_PORT = 9151
TOR_HIDDEN_SERVICE_PORT = 7475

CHUNK_SIZE = 480
HEADER_SIZE = 44

GOSSIP_INTERVAL = 30
MAX_PEERS = 50
POST_MAX_LENGTH = 500

SEED_NODES = [
]

DEMO_MODE_PEERS = []
