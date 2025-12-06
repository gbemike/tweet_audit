import csv
import json
import shutil
import tempfile
from io import StringIO
from pathlib import Path

import pytest

from config import load_config


@pytest.fixture
def temp_dirs():
    """
    Creates isolated temporary directories for each test.
    Automatically cleaned up after test completes.
    """
    temp_root = tempfile.mkdtemp()
    dirs = {
        'root': Path(temp_root),
        'output': Path(temp_root) / 'output',
        'cache': Path(temp_root) / 'cache',
        'batch_files': Path(temp_root) / 'batch_files',
    }
    
    for d in dirs.values():
        d.mkdir(exist_ok=True)
    
    yield dirs
    
    shutil.rmtree(temp_root)


@pytest.fixture
def input_js_data(temp_dirs):
    js_file = temp_dirs['root'] / "tweets.js"

    tweets_data = [
        {
            "tweet": {
                "id_str": f"tweet_{i}",
                "full_text": f"Sample tweet text {i}",
                "user": {"screen_name": f"user{i}"}
            }
        }
        for i in range(50)
    ]

    js_content = f"window.YTD.tweets.part0 = [{json.dumps(tweets_data, indent=2)}]"
    js_file.write_text(js_content, encoding="utf-8")

    return js_file, tweets_data


@pytest.fixture
def sample_tweets():
    return [
        {
            "tweet": {
                "id_str": f"tweet_{i}",
                "full_text": f"Sample text {i}",
                "user": {"screen_name": f"user{i}"}
            }
        }
        for i in range(50)
    ]


@pytest.fixture
def sample_results_json():
    user = "ekimebg"
    tweets = []
    for i in range(50):
        tweets.append({
            "explicit_words": [],
            "reason_for_flag": (
                "While not containing forbidden words or profanity, "
                f"Sample judgment text {i} could negatively impact professional reputation."
            ),
            "topic_of_tweet": [
                "personal judgment",
                "unprofessional"
            ],
            "deletion": "DELETE" if i % 2 == 0 else "KEEP",
            "tweet_id": f"19928893819513160{i}",
            "tweet_url": f"https://x.com/{user}/status/19928893819513160{i}"
        })
    return tweets


@pytest.fixture
def sample_results_csv():
    """Generate sample CSV data with only tweet_url and deletion."""
    user = "user"
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=["tweet_url", "deletion"])
    writer.writeheader()
    
    for i in range(50):
        writer.writerow({
            "tweet_url": f"https://x.com/{user}/status/19928893819513160{i}",
            "deletion": "DELETE" if i % 2 == 0 else "KEEP"
        })
    
    output.seek(0)
    return output


@pytest.fixture
def valid_config(temp_dirs):
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

    config_file = temp_dirs['root'] / "config.json"
    config_file.write_text(json.dumps(config_data))

    return load_config(str(config_file))


@pytest.fixture
def mock_batch_api(monkeypatch):
    class FakeBatchManager:
        def __init__(self, config, cache):
            self.config = config
            self.cache = cache

        def run_batch_pipeline(self, tweets, chunk_id):
            results = []
            for tweet in tweets:
                tweet_id = tweet['tweet']['id_str']
                screen_name = tweet['tweet']['user']['screen_name']
                result = {
                    "tweet_url": f"https://twitter.com/{screen_name}/status/{tweet_id}",
                    "deletion": "DELETE"
                }
                results.append(result)
                
                if self.cache and self.cache.enabled:
                    self.cache.set(tweet_id, result)
            
            return results
        
    # patch the reference inside orchestrator module, where Orchestrator uses it
    monkeypatch.setattr('orchestrator.BatchManager', FakeBatchManager)


@pytest.fixture
def mock_genai_client(monkeypatch):
    """Mock the Google GenAI client for batch operations."""
    
    fake_batch_output = """
    {"key": "tweet_1", "tweet_url": "https://x.com/user/status/tweet_1", "response": {"candidates": [{"content": {"parts": [{"text": "{\\"explicit_words\\": [], \\"reason_for_flag\\": \\"Clean\\", \\"topic_of_tweet\\": [\\"tech\\"], \\"deletion\\": \\"KEEP\\"}"}]}}]}}
    {"key": "tweet_2", "tweet_url": "https://x.com/user/status/tweet_2", "response": {"candidates": [{"content": {"parts": [{"text": "{\\"explicit_words\\": [\\"damn\\"], \\"reason_for_flag\\": \\"Profanity\\", \\"topic_of_tweet\\": [\\"rant\\"], \\"deletion\\": \\"DELETE\\"}"}]}}]}}
    """
    
    class FakeFile:
        name = "fake_file_uri_12345"
    
    class FakeJob:
        name = "fake_job_67890"
        
        class State:
            name = "JOB_STATE_SUCCEEDED"
        
        state = State()
        
        class Dest:
            file_name = "fake_result_file"
        
        dest = Dest()
    
    class FakeFiles:
        def upload(self, file, config):
            return FakeFile()
        
        def download(self, file):
            return fake_batch_output.encode("utf-8")
    
    class FakeBatches:
        def create(self, model, src, config):
            return FakeJob()
        
        def get(self, name):
            return FakeJob()
    
    class FakeClient:
        files = FakeFiles()
        batches = FakeBatches()
    
    monkeypatch.setattr('batch.genai.Client', lambda: FakeClient())
    
    return FakeClient()