import csv
import json

import pytest

from storage import Storage


def test_storage_reads_js_file_successfully(valid_config, input_js_data):
    js_file, expected_tweets = input_js_data

    storage = Storage(valid_config)
    storage.data_path = js_file
    
    loaded_tweets = storage.read_data()
    
    assert isinstance(loaded_tweets, list)
    assert len(loaded_tweets) == 50
    
    assert loaded_tweets == expected_tweets
    
    first_tweet = loaded_tweets[0]
    assert "tweet" in first_tweet
    assert "id_str" in first_tweet["tweet"]
    assert first_tweet["tweet"]["id_str"] == "tweet_0"


def test_storage_rejects_malformed_js(valid_config, temp_dirs):
    malformed_file = temp_dirs['root'] / "malformed.js"
    malformed_file.write_text("window.YTD.tweets.part0 = [ { invalid json } ]")
    
    storage = Storage(valid_config)
    storage.data_path = malformed_file
    
    with pytest.raises((ValueError, json.JSONDecodeError)):
        storage.read_data()

def test_storage_rejects_missing_file(valid_config, temp_dirs):
    missing_file = temp_dirs['root'] / "nonexistent.js"
    
    storage = Storage(valid_config)
    storage.data_path = missing_file
    
    with pytest.raises(FileNotFoundError):
        storage.read_data()


def test_storage_rejects_non_js_file(valid_config, temp_dirs):
    txt_file = temp_dirs['root'] / "tweets.txt"
    txt_file.write_text("some text")
    
    storage = Storage(valid_config)
    storage.data_path = txt_file
    
    with pytest.raises(ValueError, match=".js"):
        storage.read_data()


def test_storage_saves_chunk_json(valid_config, sample_results_json):
    storage = Storage(valid_config)
    output_file = storage.save_json(sample_results_json, chunk_id=0)
    
    assert output_file.exists()
    assert "report_chunk_0.json" in output_file.name
    
    with open(output_file, encoding="utf-8") as f:
        saved_data = json.load(f)
    
    assert isinstance(saved_data, list)
    assert len(saved_data) == len(sample_results_json)
    assert saved_data[0]["tweet_url"] == sample_results_json[0]["tweet_url"]
    assert saved_data[0]["deletion"] == sample_results_json[0]["deletion"]
    assert saved_data[0]["tweet_id"] == sample_results_json[0]["tweet_id"]


def test_storage_saves_chunk_csv(valid_config, sample_results_json):
    storage = Storage(valid_config)
    fieldnames = valid_config.processing.default_csv_fields
    output_file = storage.save_csv(sample_results_json, chunk_id=3, fieldnames=fieldnames)
    
    assert output_file.exists()
    assert "report_chunk_3.csv" in output_file.name
    
    with open(output_file, newline="", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        
        assert len(reader) == len(sample_results_json)
        
        assert set(reader[0].keys()) == set(fieldnames)
        
        for row, expected in zip(reader, sample_results_json):
            assert row["tweet_url"] == expected["tweet_url"]
            assert row["deletion"] == expected["deletion"]


def test_storage_writes_empty_json_for_no_results(valid_config):
    storage = Storage(valid_config)
    output_file = storage.save_json([], chunk_id=0)
    
    assert output_file.exists()
    
    with open(output_file) as f:
        data = json.load(f)
        assert data == []


def test_storage_writes_empty_csv_for_no_results(valid_config):
    storage = Storage(valid_config)
    fieldnames = valid_config.processing.default_csv_fields
    output_file = storage.save_csv([], chunk_id=0, fieldnames=fieldnames)
    
    assert output_file.exists()
    
    with open(output_file, encoding="utf-8") as f:
        content = f.read()
        lines = content.strip().split('\n')
        
        assert len(lines) == 1
        assert "tweet_url" in lines[0]
        assert "deletion" in lines[0]


def test_storage_merges_all_chunks(valid_config, sample_results_json):
    storage = Storage(valid_config)
    fieldnames = valid_config.processing.default_csv_fields
    
    for i in range(valid_config.processing.number_of_chunks):
        storage.save_csv(sample_results_json, chunk_id=i, fieldnames=fieldnames)
    
    storage.merge_chunks()
    
    merged_csv = storage.output_path / "merged_report.csv"
    
    assert merged_csv.exists()
    
    with open(merged_csv, newline="", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        expected_count = len(sample_results_json) * valid_config.processing.number_of_chunks
        assert len(reader) == expected_count


def test_merge_validates_chunk_count_mismatch(valid_config, sample_results_json):
    storage = Storage(valid_config)
    fieldnames = valid_config.processing.default_csv_fields
    
    for i in range(3):
        storage.save_csv(sample_results_json, chunk_id=i, fieldnames=fieldnames)
    
    with pytest.raises(ValueError):
        storage.merge_chunks()


def test_merge_fails_on_missing_chunk_files(valid_config):
    storage = Storage(valid_config)
    
    with pytest.raises(FileNotFoundError):
        storage.merge_chunks()


def test_merge_deletes_chunk_files_after_success(valid_config, sample_results_json):
    storage = Storage(valid_config)
    fieldnames = valid_config.processing.default_csv_fields
    
    for i in range(valid_config.processing.number_of_chunks):
        storage.save_json(sample_results_json, chunk_id=i)
        storage.save_csv(sample_results_json, chunk_id=i, fieldnames=fieldnames)
    
    chunk_csv_files = list(storage.output_path.glob("*chunk*.csv"))
    assert len(chunk_csv_files) == valid_config.processing.number_of_chunks

    storage.merge_chunks()

    chunk_csv_after = list(storage.output_path.glob("*chunk*.csv"))

    assert len(chunk_csv_after) == 0
    assert (storage.output_path / "merged_report.csv").exists()

