import csv

from cache import CacheManager
from orchestrator import Orchestrator
from storage import Storage


def test_orchestrator_initializes_from_config(valid_config, mock_genai_client):
    cache = CacheManager(valid_config)
    storage = Storage(valid_config)

    orchestrator = Orchestrator(valid_config, storage, cache)

    assert len(orchestrator.fieldnames) == 2
    assert orchestrator.config == valid_config
    assert orchestrator.cache == cache
    assert orchestrator.storage == storage
    assert orchestrator.chunker is not None
    assert orchestrator.batch_manager is not None


def test_orchestrator_processes_chunk_successfully(valid_config, sample_tweets, mock_batch_api):
    cache = CacheManager(valid_config)
    storage = Storage(valid_config)
    orchestrator = Orchestrator(valid_config, storage, cache)
    
    orchestrator.run(sample_tweets, chunk_id=0)
    
    json_file = storage.output_path / "report_chunk_0.json"
    csv_file = storage.output_path / "report_chunk_0.csv"
    
    assert json_file.exists()
    assert csv_file.exists()


def test_orchestrator_filters_csv_data(valid_config, sample_tweets, mock_batch_api):
    cache = CacheManager(valid_config)
    storage = Storage(valid_config)
    orchestrator = Orchestrator(valid_config, storage, cache)
    
    orchestrator.run(sample_tweets, chunk_id=0)
    
    csv_file = storage.output_path / "report_chunk_0.csv"
    
    with open(csv_file, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        
        # check for tweet_url and deletion
        assert set(rows[0].keys()) == {"tweet_url", "deletion"}
        
        assert len(rows) > 0


def test_orchestrator_process_single_chunk_workflow(valid_config, sample_tweets, mock_batch_api):
    cache = CacheManager(valid_config)
    storage = Storage(valid_config)
    orchestrator = Orchestrator(valid_config, storage, cache)
    
    chunk_data = orchestrator.chunker.get_chunk(sample_tweets, chunk_id=1)
    
    orchestrator._process_single_chunk(1, chunk_data)
    
    json_file = storage.output_path / "report_chunk_1.json"
    csv_file = storage.output_path / "report_chunk_1.csv"
    
    assert json_file.exists()
    assert csv_file.exists()


def test_orchestrator_multiple_chunks_independent(valid_config, sample_tweets, mock_batch_api):
    storage = Storage(valid_config)
    orchestrator = Orchestrator(valid_config, storage)
    
    orchestrator.run(sample_tweets, chunk_id=0)
    orchestrator.run(sample_tweets, chunk_id=1)
    orchestrator.run(sample_tweets, chunk_id=2)
    
    for chunk_id in [0, 1, 2]:
        json_file = storage.output_path / f"report_chunk_{chunk_id}.json"
        csv_file = storage.output_path / f"report_chunk_{chunk_id}.csv"
        
        assert json_file.exists()
        assert csv_file.exists()
