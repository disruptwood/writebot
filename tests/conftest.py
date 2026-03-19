import os
import sys

import pytest

# Ensure bot package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Override config before importing bot modules
os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("CHANNEL_ID", "-1001234567890")
os.environ.setdefault("DISCUSSION_GROUP_ID", "-1009876543210")
