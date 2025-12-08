# Tweet Audit Pipeline

A high-performance, parallel tweet auditing system that uses Google's Gemini API to analyze tweets against configurable criteria and flag content for deletion.

## Overview

The Tweet Audit Pipeline processes large Twitter archives by:

* **Parallel Processing** : Splits data into chunks processed simultaneously
* **Smart Caching** : Avoids reprocessing already-analyzed tweets
* **Batch API Integration** : Efficiently processes tweets via Google Gemini Batch API
* **Automated Merging** : Combines parallel results into unified reports

 **Performance** : Processes 3,000 tweets in <5 minutes (vs 2 hours sequentially)

## Architecture

```
┌─────────────┐
│ Shell Script│ (Coordinator)
└──────┬──────┘
       │ Spawns N workers in parallel
       ├────────┬────────┬────────┬────────┐
       ▼        ▼        ▼        ▼        ▼
   Worker 0  Worker 1  Worker 2  Worker 3  Worker 4
   (Chunk 0) (Chunk 1) (Chunk 2) (Chunk 3) (Chunk 4)
       │        │        │        │        │
       ├────────┴────────┴────────┴────────┤
       │      Each worker independently:    │
       │      1. Extracts its chunk         │
       │      2. Filters cached tweets      │
       │      3. Calls Batch API            │
       │      4. Saves results              │
       └────────┬────────┬────────┬────────┘
                │        │        │
                ▼        ▼        ▼
         chunk_0.json  chunk_1.json  chunk_2.json ...
                │        │        │
                └────────┴────────┘
                         ▼
                  Merge Results
                         ▼
              merged_report.csv
```

## Prerequisites

* Python 3.11 or higher.
* [Poetry](https://python-poetry.org/) for dependency management.
* At least a Tier 1 API KEY, Google Gemini API key ([get one here](https://ai.google.dev/)). The tool uses Geminis Batch API which cannot be used on a free tier.

## Installation and Setup

```bash
# macOS/Linux (Install Poetry)
curl -sSL https://install.python-poetry.org | python3 -

# Or via pip
pip install poetry

# Clone repository
git clone <repository-url>
cd tweet_audit

# Create virtual environment
python -m venv venv

# Activate virtual environment Linux
source venv/bin/activate

# Windows
venv/Scripts/activate

# install project dependencies
poetry install

# Set environment variables
export GOOGLE_API_KEY=your_gemini_api_key

# In .env, set
CONFIG_PATH="YOUR_CONFIG_PATH"
GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
```

## Configuration

Create `config.json`, fill in `criteria` and `username` (your twitter username).

```json
{
"criteria": {
    "forbidden_words": ["profanity1", "profanity2"],
    "topics_to_exclude": ["topic_1", "topic-2"],
    "tone_requirements": ["tone_1", "tone_1"],
    "additional_instructions": "polite twwets only"
  },
  "cache": {
    "directory": "cache/.tweet_cache/",
    "enabled": true
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
    "directory": "data/batch_requests/"
  },
  "run_defaults": {
    "file_path": "data/raw/tweets/tweets.js",
    "output_path": "data/processed/tweet_audit_files/",
    "clear_cache": true
  },
  "url_builder": {
    "user": "your_username",
    "base_url": "https://x.com/{user}/status/{id}"
  }
}
```

## Usage

Create a directory within the project called `data/raw/tweets ` then download your tweets from X , with your downloaded data take the file called `tweets.js` and place it within the `data/raw/tweets` directory.

### Run Full Pipeline (Parallel)

```bash
./run_pipeline.sh
```

This script:

1. Validates configuration
2. Spawns N parallel workers (one per chunk)
3. Waits for all workers to complete
4. Merges results if all succeed

### Run Single Chunk (For Testing)

```bash
poetry run python src/main.py --chunk-id 1
```

### Merge Results Manually

```bash
poetry run python src/merge_chunks.py
```

## Pipeline Workflow

### Stage 0: Shell Orchestration

* Reads `number_of_chunks` from config
* Validates `NUM_CHUNKS` doesn't exceed config limit
* Spawns N workers in parallel with unique `chunk_id`
* Monitors exit codes
* Triggers merge only if all workers succeed

### Stage 1: Configuration Load

* Loads and validates `config.json`
* Initializes all modules (Cache, Storage, Chunker, BatchManager)
* Creates `Orchestrator` via dependency injection

### Stage 2: Data Acquisition

* Storage reads `.js` file from Twitter archive
* Extracts JSON array using regex
* Returns full tweet dataset

### Stage 3: Chunking & Filtering

* **Chunking** : Round-robin distribution (`index % num_chunks == chunk_id`)
* **Cache Filtering** : Checks `cache.exists(tweet_id)` for each tweet
* Returns only uncached tweets for processing

### Stage 4: Batch API Processing

1. **Create Batch File** : Generates JSONL with one request per tweet
2. **Upload** : Sends file to Google File API
3. **Submit Job** : Creates batch job with Gemini model
4. **Poll Status** : Checks job state every 30s until `SUCCEEDED`
5. **Download Results** : Retrieves JSONL output
6. **Parse & Validate** : Extracts JSON responses, validates schema
7. **Cache Results** : Saves to cache for future runs

### Stage 5: Save Results

* Writes chunk JSON: `report_chunk_N.json` (full results)
* Writes chunk CSV: `report_chunk_N.csv` (filtered: tweet_url, deletion)

### Stage 6: Merge

* Validates expected chunk count matches actual files
* Combines all JSON chunks into `merged_report.json`
* Combines all CSV chunks into `merged_report.csv`
* Deletes individual chunk files
* Releases cache lock for next run

## Output Format

### JSON Output

```json
[
  {
    "tweet_id": "1234567890",
    "tweet_url": "https://x.com/user/status/1234567890",
    "explicit_words": ["damn"],
    "reason_for_flag": "Contains mild profanity",
    "topic_of_tweet": ["complaint", "frustration"],
    "deletion": "DELETE"
  }
]
```

### CSV Output

```csv
tweet_url,deletion
https://x.com/user/status/1234567890,DELETE
https://x.com/user/status/1234567891,KEEP
```

## Testing

```bash
# Run all tests
poetry run pytest tests/ -v

# Run specific test file
poetry run pytest tests/test_cache.py -v
```

## Project Structure

```
tweet-audit/
├── cache/
├── data/
├── logs/
├── src/
│   ├── config.py          # Configuration loading
│   ├── cache.py           # Cache management
│   ├── storage.py         # File I/O operations
│   ├── chunker.py         # Data partitioning
│   ├── batch.py           # Batch API integration
│   ├── orchestrator.py    # Workflow coordination
│   ├── merge_chunks.py    # Result merging
│   └── main.py            # Entry point
├── tests/
│   └── ...                # Integration tests
├── run_pipeline.sh        # Shell orchestrator
├── config.json            # Configuration
├── pyproject.toml         # Package definition
└── pytest.ini             # Test configuration
```

---
