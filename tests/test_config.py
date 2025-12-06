import json

import pytest

from cache import CacheManager
from config import load_config
from storage import Storage


def test_valid_config_loads(temp_dirs):
    config_data = {
        "criteria": {
            "forbidden_words": ["fuck", "shit"],
            "topics_to_exclude": ["Outdated opinions", "Controversial statements"],
            "tone_requirements": ["Professional language only"],
            "additional_instructions": (
                "Flag any content that could harm professional reputation "
                "and contains any sort of profanity"
            )
        },
        "cache": {
            "directory": str(temp_dirs['cache']),
            "enabled": True
        },
        "processing": {
            "number_of_chunks": 5,
            "default_csv_fields": ["tweet_url", "deletion"]
        },
        "model": {
            "primary": "gemini-2.5-flash-lite",
            "secondary": "gemini-2.5-flash",
            "max_retries": 3
        },
        "batch_files": {
            "directory": str(temp_dirs['batch_files'])
        },
        "run_defaults": {
            "file_path": str(temp_dirs['root'] / "tweets.js"),
            "output_path": str(temp_dirs['output']),
            "clear_cache": False
        },
        "url_builder": {
            "user": "user",
            "base_url": "https://x.com/{user}/status/{id}"
        }
    }
    
    config_file = temp_dirs['root'] / 'config.json'
    with open(config_file, 'w') as f:
        json.dump(config_data, f)
    
    config = load_config(str(config_file))
    
    assert config.processing.number_of_chunks
    assert config.url_builder.base_url == "https://x.com/{user}/status/{id}"
    assert type(config.cache.enabled) == bool


def test_malformed_json_fails(temp_dirs):
    config_file = temp_dirs['root'] / 'config.json'
    config_file.write_text('{ invalid json')

    with pytest.raises(ValueError):
        load_config(str(config_file))


def test_missing_file_fails(temp_dirs):
    with pytest.raises(FileNotFoundError):
        load_config(str(temp_dirs['root'] / 'missing.json'))


def test_config_initializes_modules(valid_config):
    cache = CacheManager(valid_config)
    storage = Storage(valid_config)
    
    assert cache.enabled == valid_config.cache.enabled
    assert storage.output_path.exists()