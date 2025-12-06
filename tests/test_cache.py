import json
import pickle
from dataclasses import asdict

from cache import CacheManager
from chunker import Chunker
from config import load_config
from orchestrator import Orchestrator
from storage import Storage


def test_cache_initializes_from_config(valid_config):
    cache = CacheManager(valid_config)
    
    assert cache.enabled is True
    assert cache.cache_dir.exists()


def test_cache_disabled_no_operations(temp_dirs, valid_config):
    config_data = asdict(valid_config)
    config_data['cache']['enabled'] = False
    
    config_file = temp_dirs["root"] / "config_disabled_cache.json"
    config_file.write_text(json.dumps(config_data))
    
    cfg = load_config(str(config_file))
    cache = CacheManager(cfg)
    
    cache.set("tweet_1", {"deletion": "test"})
    assert not cache.exists("tweet_1")


def test_cache_clear_deletes_files(temp_dirs, valid_config):
    cache = CacheManager(valid_config)

    with open(temp_dirs['cache'] / 'tweet_1.pkl', 'wb') as f:
        pickle.dump({}, f)
    with open(temp_dirs['cache'] / 'tweet_2.pkl', 'wb') as f:
        pickle.dump({}, f)
    
    cache.clear()
    
    remaining = list(temp_dirs['cache'].glob('*.pkl'))
    assert len(remaining) == 0


def test_chunker_uses_cache_to_filter(sample_tweets, valid_config):
    cache = CacheManager(valid_config)
    chunker = Chunker(valid_config, cache)
    
    first_tweet_id = sample_tweets[0]['tweet']['id_str']
    cache.set(first_tweet_id, {'deletion': 'KEEP'})
    
    chunk_0 = chunker.get_chunk(sample_tweets, chunk_id=0)
    
    ids = [t['tweet']['id_str'] for t in chunk_0]
    assert first_tweet_id not in ids

def test_chunker_with_all_tweets_cached_returns_empty(valid_config, sample_tweets):
    cache = CacheManager(valid_config)
    chunker = Chunker(valid_config, cache)
    
    # cache all tweets for chunk 0 (0, 5, 10, 15...)
    for i in range(0, len(sample_tweets), valid_config.processing.number_of_chunks):
        tweet_id = sample_tweets[i]['tweet']['id_str']
        cache.set(tweet_id, {'deletion': 'KEEP'})
    
    chunk_0 = chunker.get_chunk(sample_tweets, chunk_id=0)
    
    assert len(chunk_0) == 0

def test_chunker_without_cache_no_filtering(valid_config, sample_tweets):
    chunker = Chunker(valid_config, cache=None)
    
    chunk_0 = chunker.get_chunk(sample_tweets, chunk_id=0)
    
    # 50 tweets / 5 chunks = 10 per chunk
    assert len(chunk_0) == 10


def test_chunker_with_disabled_cache_no_filtering(valid_config, sample_tweets, temp_dirs):
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
            "enabled": False
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
    cache = CacheManager(config)
    chunker = Chunker(config, cache)
    
    cache.set('tweet_0', {'deletion': 'KEEP'})
    
    chunk_0 = chunker.get_chunk(sample_tweets, chunk_id=0)
    
    tweet_ids = [t['tweet']['id_str'] for t in chunk_0]
    assert 'tweet_0' in tweet_ids


def test_batch_results_cached(valid_config, sample_tweets, mock_batch_api):
    cache = CacheManager(valid_config)
    storage = Storage(valid_config)
    orchestrator = Orchestrator(valid_config, storage, cache)
    
    chunk = [sample_tweets[0]]
    orchestrator._process_single_chunk(0, chunk)
    
    assert cache.exists('tweet_0')

def test_cache_lock_prevents_concurrent_clears(valid_config, temp_dirs):
    """Only first process clears cache, others skip due to lock."""
    cache1 = CacheManager(valid_config)
    cache2 = CacheManager(valid_config)
    
    with open(temp_dirs['cache'] / 'tweet_1.pkl', 'wb') as f:
        pickle.dump({'data': 'test'}, f)
    with open(temp_dirs['cache'] / 'tweet_2.pkl', 'wb') as f:
        pickle.dump({'data': 'test'}, f)
    
    # first clear acquires lock and clears files
    cache1.clear()
    
    remaining = list(temp_dirs['cache'].glob('*.pkl'))
    assert len(remaining) == 0
    
    assert cache1.lock_path.exists()
    
    with open(temp_dirs['cache'] / 'tweet_3.pkl', 'wb') as f:
        pickle.dump({'data': 'test'}, f)
    
    cache2.clear()
    
    remaining = list(temp_dirs['cache'].glob('*.pkl'))
    assert len(remaining) == 1
    
    assert cache2.lock_path.exists()