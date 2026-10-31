"""Separate read-only bundle assets from portable, persistent user files."""
from pathlib import Path
import sys


def resource_root():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))


def user_data_root():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def user_sounds_root():
    return user_data_root() / 'user_sounds'
