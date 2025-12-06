import json

import pytest

from cache import CacheManager
from chunker import Chunker
from config import load_config


def test_chunker_initializes_from_config(valid_config):
    cache = CacheManager(valid_config)
    chunker = Chunker(valid_config, cache)
    
    assert chunker.number_of_chunks == 5
    assert chunker.cache is not None


def test_chunker_rejects_invalid_number_of_chunks(temp_dirs):
    config_data = {
        "criteria": {
            "forbidden_words": ["test"],
            "topics_to_exclude": [],
            "tone_requirements": [],
            "additional_instructions": ""
        },
        "cache": {
            "directory": str(temp_dirs['cache']),
            "enabled": True
        },
        "processing": {
            "number_of_chunks": 0,  # invalid
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
    
    config_file = temp_dirs['root'] / "config_zero_chunks.json"
    config_file.write_text(json.dumps(config_data))
    
    config = load_config(str(config_file))
    
    with pytest.raises(ValueError, match="number_of_chunks must be > 0"):
        Chunker(config)
    
    
    # test with a negative
    config_data['processing']['number_of_chunks'] = -5
    config_file_neg = temp_dirs['root'] / "config_neg_chunks.json"
    config_file_neg.write_text(json.dumps(config_data))
    
    config_neg = load_config(str(config_file_neg))
    
    with pytest.raises(ValueError, match="number_of_chunks must be > 0"):
        Chunker(config_neg)


def test_chunker_distribution(valid_config, sample_tweets):
    chunker = Chunker(valid_config, cache=None)
    
    chunk_0 = chunker.get_chunk(sample_tweets, chunk_id=0)
    chunk_1 = chunker.get_chunk(sample_tweets, chunk_id=1)
    chunk_2 = chunker.get_chunk(sample_tweets, chunk_id=2)
    
    assert chunk_0[0]['tweet']['id_str'] == 'tweet_0'
    assert chunk_0[1]['tweet']['id_str'] == 'tweet_5'
    assert chunk_0[2]['tweet']['id_str'] == 'tweet_10'
    
    assert chunk_1[0]['tweet']['id_str'] == 'tweet_1'
    assert chunk_1[1]['tweet']['id_str'] == 'tweet_6'
    assert chunk_1[2]['tweet']['id_str'] == 'tweet_11'
    
    assert chunk_2[0]['tweet']['id_str'] == 'tweet_2'
    assert chunk_2[1]['tweet']['id_str'] == 'tweet_7'
    assert chunk_2[2]['tweet']['id_str'] == 'tweet_12'


def test_all_chunks_cover_all_tweets(valid_config, sample_tweets):
    chunker = Chunker(valid_config, cache=None)
    
    all_chunk_tweets = []
    for chunk_id in range(valid_config.processing.number_of_chunks):
        chunk = chunker.get_chunk(sample_tweets, chunk_id)
        all_chunk_tweets.extend(chunk)
    
    assert len(all_chunk_tweets) == len(sample_tweets)
    
    tweet_ids = [t['tweet']['id_str'] for t in all_chunk_tweets]
    assert len(tweet_ids) == len(set(tweet_ids))


def test_chunker_rejects_invalid_chunk_id(valid_config, sample_tweets):
    chunker = Chunker(valid_config, cache=None)
    
    # chunk_id too high
    with pytest.raises(ValueError, match="out of range"):
        chunker.get_chunk(sample_tweets, chunk_id=5)
    
    with pytest.raises(ValueError, match="out of range"):
        chunker.get_chunk(sample_tweets, chunk_id=100)
    
    # negative chunk_id
    with pytest.raises(ValueError, match="out of range"):
        chunker.get_chunk(sample_tweets, chunk_id=-1)


def test_chunker_handles_tweets_with_missing_id(valid_config):
    cache = CacheManager(valid_config)
    chunker = Chunker(valid_config, cache)
    
    tweets_with_missing_ids = [
        {"tweet": {"id_str": "tweet_0", "full_text": "valid"}},
        {"tweet": {"full_text": "missing id"}},
        {"tweet": {"id_str": "tweet_5", "full_text": "valid"}},
        {"tweet": {"id_str": None, "full_text": "null id"}},
    ]
    
    chunk_0 = chunker.get_chunk(tweets_with_missing_ids, chunk_id=2)
    
    tweet_ids = [t['tweet']['id_str'] for t in chunk_0]
    assert 'tweet_5' in tweet_ids


def test_chunker_handles_empty_tweet_list(valid_config):
    chunker = Chunker(valid_config, cache=None)
    
    chunk_0 = chunker.get_chunk([], chunk_id=0)
    
    assert chunk_0 == []


def test_chunker_with_uneven_tweet_count(valid_config):
    chunker = Chunker(valid_config, cache=None)
    
    tweets = [
        {"tweet": {"id_str": f"tweet_{i}", "full_text": f"text {i}"}}
        for i in range(47)
    ]
    
    chunk_sizes = []
    for chunk_id in range(valid_config.processing.number_of_chunks):
        chunk = chunker.get_chunk(tweets, chunk_id)
        chunk_sizes.append(len(chunk))
    
    assert chunk_sizes == [10, 10, 9, 9, 9]


def test_chunker_preserves_tweet_structure(valid_config, sample_tweets):
    chunker = Chunker(valid_config, cache=None)
    
    original_first_tweet = sample_tweets[0]
    chunk_0 = chunker.get_chunk(sample_tweets, chunk_id=0)
    chunked_first_tweet = chunk_0[0]
    
    assert chunked_first_tweet == original_first_tweet
    assert chunked_first_tweet['tweet']['id_str'] == original_first_tweet['tweet']['id_str']
    assert chunked_first_tweet['tweet']['full_text'] == original_first_tweet['tweet']['full_text']