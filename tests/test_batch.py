import json
from pathlib import Path

from batch import BatchManager
from cache import CacheManager


def test_batch_manager_initializes_from_config(valid_config, mock_genai_client):
    cache = CacheManager(valid_config)
    batch_manager = BatchManager(valid_config, cache)
    
    assert batch_manager.model == valid_config.model.primary
    assert batch_manager.max_retries == valid_config.model.max_retries
    assert batch_manager.batch_path.exists()
    assert batch_manager.user == valid_config.url_builder.user


def test_batch_manager_creates_batch_directory(valid_config, temp_dirs, mock_genai_client):
    batch_dir = temp_dirs['batch_files']
    batch_dir.rmdir()
    
    assert not batch_dir.exists()
    
    batch_manager = BatchManager(valid_config)
    
    assert batch_manager.batch_path.exists()


def test_create_prompt_includes_criteria(valid_config, mock_genai_client):
    batch_manager = BatchManager(valid_config)
    
    tweet_text = "This is a test tweet"
    prompt = batch_manager._create_prompt(tweet_text)
    
    assert "fuck" in prompt
    assert "shit" in prompt
    assert "Outdated opinions" in prompt
    assert "Professional language only" in prompt
    
    assert tweet_text in prompt
    
    assert "JSON" in prompt
    assert "DELETE" in prompt
    assert "KEEP" in prompt


def test_create_batch_file_generates_jsonl(valid_config, sample_tweets, mock_genai_client, temp_dirs):
    batch_manager = BatchManager(valid_config)
    
    tweets_subset = sample_tweets[:5]
    chunk_id = 0

    file = batch_manager.create_batch_file(tweets_subset, chunk_id)
    
    batch_file_path = batch_manager.batch_path / f"batch_chunk_{chunk_id}.jsonl"

    assert file.name == "files/1234567890" 
    
    with open(batch_file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    
        
    assert len(lines) == 5
    
    for line in lines:
        obj = json.loads(line)
        assert "key" in obj
        assert "tweet_url" in obj
        assert "request" in obj


def test_parse_response_valid_json(valid_config, mock_genai_client):
    batch_manager = BatchManager(valid_config)
    
    response_text = """
    {
        "explicit_words": ["damn"],
        "reason_for_flag": "Contains mild profanity",
        "topic_of_tweet": ["complaint"],
        "deletion": "DELETE"
    }
    """
    
    result = batch_manager._parse_response(response_text, "tweet_123", "https://x.com/user/status/123")
    
    assert result is not None
    assert result["explicit_words"] == ["damn"]
    assert result["reason_for_flag"] == "Contains mild profanity"
    assert result["topic_of_tweet"] == ["complaint"]
    assert result["deletion"] == "DELETE"


def test_parse_response_with_markdown_wrapper(valid_config, mock_genai_client):
    batch_manager = BatchManager(valid_config)
    
    response_text = """
    ```json
    {
        "explicit_words": [],
        "reason_for_flag": "Clean tweet",
        "topic_of_tweet": ["tech"],
        "deletion": "KEEP"
    }
    ```
    """
    
    result = batch_manager._parse_response(response_text, "tweet_456", "url")
    
    assert result is not None
    assert result["topic_of_tweet"] == ["tech"]
    assert result["deletion"] == "KEEP"


def test_parse_response_missing_required_keys(valid_config, mock_genai_client):
    batch_manager = BatchManager(valid_config)
    
    response_text = """
    {
        "explicit_words": [],
        "reason_for_flag": "Test",
        "topic_of_tweet": ["tech"]
    }
    """
    
    result = batch_manager._parse_response(response_text, "tweet_789", "url")
    
    assert result is None


def test_parse_response_malformed_json(valid_config, mock_genai_client):
    batch_manager = BatchManager(valid_config)
    
    response_text = "{ this is not valid json }"
    
    result = batch_manager._parse_response(response_text, "tweet_999", "url")
    
    assert result is None


def test_parse_response_extracts_json_from_text(valid_config, mock_genai_client):
    batch_manager = BatchManager(valid_config)
    
    response_text = """
    Here's the analysis:
    {
        "explicit_words": [],
        "reason_for_flag": "Tweet is appropriate",
        "topic_of_tweet": ["news"],
        "deletion": "KEEP"
    }
    Additional notes here.
    """
    
    result = batch_manager._parse_response(response_text, "tweet_111", "url")
    
    assert result is not None
    assert result["deletion"] == "KEEP"


def test_run_batch_pipeline_with_empty_tweets(valid_config, mock_genai_client):
    batch_manager = BatchManager(valid_config)
    
    results = batch_manager.run_batch_pipeline([], chunk_id=0)
    
    assert results == []


def test_batch_manager_url_building(valid_config, sample_tweets, mock_genai_client):
    batch_manager = BatchManager(valid_config)
    tweet_id = sample_tweets[0]['tweet']['id_str']
    
    expected_url = f"https://x.com/{valid_config.url_builder.user}/status/{tweet_id}"
    
    actual_url = batch_manager.base_url.format(
        user=batch_manager.user, 
        id=tweet_id
    )

    assert actual_url == expected_url

def test_full_batch_pipeline(valid_config, sample_tweets, mock_genai_client):
    cache = CacheManager(valid_config)
    batch_manager = BatchManager(valid_config, cache=cache)
    file = batch_manager.create_batch_file(tweets=sample_tweets, chunk_id=1)

    assert file.name == "files/1234567890" 

    job = batch_manager._submit_batch_with_retry(file.name, chunk_id=1)

    completed_job = batch_manager._poll_job_until_complete(job)

    assert completed_job.state.name == "JOB_STATE_SUCCEEDED"

    results = batch_manager.handle_results(job)

    assert isinstance(results, list)
    
    assert len(results) == 3
    
    assert 'deletion' in results[0]
    

    assert results[0]['tweet_id'] == "tweet_0"
    assert results[0]['deletion'] == "DELETE"
    assert results[0]['reason_for_flag'] == "Profanity" 

    assert results[1]['tweet_id'] == "tweet_1"
    assert results[1]['deletion'] == "KEEP"
    assert results[1]['topic_of_tweet'] == ['tech']    
    
