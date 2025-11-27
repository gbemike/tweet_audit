import asyncio
import json
import logging
import os
import pickle
import re
import time
import sys
import argparse
from dotenv import load_dotenv

import traceback
from collections import Counter
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types
from tqdm import tqdm

load_dotenv()

CONFIG_PATH = os.getenv("CONFIG_PATH")

# load config
try:
    with open(CONFIG_PATH, "r") as f:
        CONFIG = json.load(f)
except FileNotFoundError:
    print("Error: config.json not found. Please create one.")
    sys.exit(1)


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)

CACHE_DIR = Path(CONFIG["cache"]["directory"])
NUMBER_OF_CHUNKS = CONFIG.get("processing", {}).get("number_of_chunks", 5) # default to 5

class TweetCache:
    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True, parents=True)
        self.cache_enabled = True

    def _get_file_path(self, tweet_id: str) -> Path:
        """Helper to create consistent filenames based on Tweet ID."""
        safe_id = str(tweet_id).strip()
        return self.cache_dir / f"tweet_{safe_id}.pkl"

    def get(self, tweet_id: str) -> Optional[Dict]:
        """
        Retrieves cached data using the Tweet ID string.
        """
        if not self.cache_enabled:
            logger.debug("Cache is disabled, skipping lookup")
            return None
        
        cache_file = self._get_file_path(tweet_id)

        if not cache_file.exists():
            logger.debug(f"Cache MISS for ID: {tweet_id}")
            return None
    
        try:
            with open(cache_file, 'rb') as f:
                cached_data = pickle.load(f)
                logger.debug(f"Cache HIT for ID: {tweet_id}")
                return cached_data
        except Exception as e:
            logger.warning(f"Failed to load cache for {tweet_id}: {e}. Deleting file.")
            logger.debug(f"Exception: {traceback.format_exc()}")
            cache_file.unlink(missing_ok=True)
            return None

    def set(self, tweet_id: str, chunk_id: Optional[int], result: Any):
        """
        Saves result to cache using the Tweet ID string.
        """
        if not self.cache_enabled:
            logger.debug("Cache is disabled, skipping set operation")
            return

        if chunk_id is None:
            safe_chunk_id = -1
        else:
            safe_chunk_id = chunk_id
        
        result['chunk_id'] = safe_chunk_id
        cache_file = self._get_file_path(tweet_id)
        
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(result, f)
            logger.debug(f"Cached result for ID: {tweet_id} Chunk {chunk_id}")
        except Exception as e:
            logger.warning(f"Failed to cache result for {tweet_id}: {e}")
            logger.debug(f"Exception: {traceback.format_exc()}")

    def clear(self):
        if not self.cache_dir.exists():
            logger.warning(f"Cache directory does not exist: {self.cache_dir}")
            return 0
        
        cache_files = list(self.cache_dir.glob("*.pkl"))
        
        if not cache_files:
            logger.info("No cache files to clear")
            return 0
        
        cleared_count = 0
        failed_count = 0
        
        for cache_file in cache_files:
            try:
                cache_file.unlink()
                cleared_count += 1
            except Exception as e:
                failed_count += 1
                logger.error(f"Failed to delete {cache_file.name}: {e}")
        
        logger.info(f"Cache cleared: {cleared_count} deleted, {failed_count} failed")
        return cleared_count

    def get_stats(self) -> Dict[str, Any]:
        if not self.cache_dir.exists():
            return {
                'total_entries': 0,
                'cache_enabled': self.cache_enabled,
                'cache_dir': str(self.cache_dir),
                'cache_dir_exists': False,
            }
        
        cache_files = list(self.cache_dir.glob("*.pkl"))
        total_size = sum(f.stat().st_size for f in cache_files)
          
        stats = {
            'total_entries': len(cache_files),
            'cache_enabled': self.cache_enabled,
            'cache_file_exists': True,
            'total_size_bytes': total_size,
            'total_size_kb': round(total_size / 1024, 2),
        }
        
        logger.info(f"Cache stats: {stats}")
        return stats
    
    def set_cache_status(self, enabled: bool):
        self.cache_enabled = enabled
        logger.info(f"Cache {'enabled' if enabled else 'disabled'}")


class AuditTweet:
    def __init__(self):
        logger.info("="*60)
        logger.info("Initializing AuditTweet")
        logger.info("="*60)

        # laod cache
        self.cache = TweetCache(CACHE_DIR)
        self.cache.set_cache_status(CONFIG["cache"]["enabled"])
        
        # configure gemini api
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            logger.error("GEMINI_API_KEY environment variable not set")
            # In a full script, you might raise here, but for demonstration, we continue.
            raise ValueError("GEMINI_API_KEY environment variable not set.")
        
        # only load client if API key is present
        self.client = genai.Client(api_key=api_key) if api_key else None
        
        self.model = CONFIG["model"]["primary"]
        self.max_retries = CONFIG["model"]["max_retries"]

        logger.info(f"Primary model: {self.model}")
        logger.info(f"AuditTweet initialization complete")


    def read_archive_data(self, data_path: str) -> List[Dict]:
        """
        get tweet data from archive .js file.
        """
        data_file = Path(data_path)

        if not data_file.exists():
            logger.error(f"Data file not found: {data_path}")
            raise FileNotFoundError(f"Data file not found: {data_path}")
        
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                content = f.read()
            match = re.search(r"\[\s*{.*}\s*\]", content, flags=re.DOTALL)
            if not match:
                raise ValueError("No JSON array found.")
            json_array_str = match.group(0)
            data = json.loads(json_array_str)
            logger.info(f"Successfully loaded {len(data)} tweets from archive with type {type(data)}")
            return data
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from {data_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to read archive data: {e}")
            raise

    def split_into_chunks(self, data: List[Dict], chunk_id: int) -> List[Dict]:
        """
        filters the full list of tweets to return only the tweets belonging to the chunk id specified
        """
        if chunk_id < 0 or chunk_id >= NUMBER_OF_CHUNKS:
             raise ValueError(f"chunk_id {chunk_id} is out of range (0-{NUMBER_OF_CHUNKS-1})")
        
        chunk_tweets = []

        for i, tweet in enumerate(data):
            if i % NUMBER_OF_CHUNKS == chunk_id:
                chunk_tweets.append(tweet)

        logger.info(f"Filtered to Chunk {chunk_id}: {len(chunk_tweets)} tweets for processing.")
        
        return chunk_tweets


    def _create_analysis_prompt(self, tweet_text: str) -> str:
        """Create analysis prompt for a tweet."""
        return f"""
        Analyze this tweet and determine if it should be flagged for deletion.

        Tweet: "{tweet_text}"

        Criteria for flagging:
        - Contains unprofessional language
        - Contains outdated opinions
        - Contains specific keywords to avoid
        - Any content with insults, profanity and unethical outrage

        Respond ONLY in JSON format:
        {{
            "explicit_words": ["<explicit word as they appear in the tweet, or empty list if none>"],
            "reason_for_flag": "<A brief explanation>",
            "topic_of_tweet": ["<controlled_taxonomy_labels>"],
            "flag": [<True or False>]
        }}
        """
    
    def _parse_analysis_response(self, response_text: str, tweet_id: str) -> Optional[Dict]:
        try: 
            match = re.search(r"\{.*\}", response_text, re.DOTALL)
            
            if match:
                json_str = match.group(0)
            else:
                json_str = response_text.strip()

            data = json.loads(json_str)
            required_keys = ["explicit_words", "reason_for_flag", "topic_of_tweet"]
            if not all(key in data for key in required_keys):
                logger.warning(f"Tweet {tweet_id}: Response missing required keys. Keys found: {list(data.keys())}")
                return None
            
            return data

        except json.JSONDecodeError as e:
            logger.error(f"Tweet {tweet_id}: Failed to parse JSON. Error: {e}")
            logger.debug(f"Raw Content causing error: {response_text}")
            return None
        except Exception as e:
            logger.error(f"Tweet {tweet_id}: Unexpected error parsing response: {e}")
            return None

    def create_batch_file(self, all_tweets: List[Dict], chunk_id: int) -> types.File:
        """Creates local JSONL file, uploads it, and returns the uploaded file object."""
        
        if not self.client:
             raise ConnectionError("Gemini Client not initialized. Check API Key.")
             
        # batch_file = Path(f"outputs/)batch_chunk_{chunk_id}.jsonl")

        batch_file_path = CONFIG['batch_files']['directory']
        batch_file = Path(batch_file_path) / f"batch_chunk_{chunk_id}.jsonl"
        batch_file.parent.mkdir(parents=True, exist_ok=True)        

        logger.info(f"[Chunk {chunk_id}] Creating local batch file with {len(all_tweets)} tweets")

        with open(batch_file, "w", encoding="utf-8") as f:
            for tweet in all_tweets:
                tweet_data = tweet.get("tweet", {})
                tweet_id = str(tweet_data.get("id_str") or tweet_data.get("id", "unknown"))
                tweet_text = tweet_data.get("full_text", "")

                request_obj = {
                    "key": tweet_id, # use key for easy lookup in results
                    "request": {
                        "contents": [{
                            "parts": [{
                                "text": self._create_analysis_prompt(tweet_text)
                            }]
                        }]
                    }
                }
                f.write(json.dumps(request_obj, ensure_ascii=False) + "\n")

        # upload the file
        logger.info(f"[Chunk {chunk_id}] Uploading batch file...")
        uploaded_file = self.client.files.upload(
            file=batch_file,
            config=types.UploadFileConfig(
                display_name=f'audit_chunk_{chunk_id}',
                mime_type='jsonl'
                ),
        )

        logger.info(f"[Chunk {chunk_id}] Uploaded file created: {uploaded_file.name}")
        return uploaded_file
    
    def _create_batch_job_with_retry(self, uploaded_file_name: str, chunk_id: int) -> Optional[types.BatchJob]:
        """
        Submits a batch job with exponential backoff to handle 429 RESOURCE_EXHAUSTED errors.
        """
        job = None
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Attempt {attempt + 1}/{self.max_retries}: Starting batch job for chunk {chunk_id}...")
                
                job = self.client.batches.create(
                    model=self.model,
                    src=uploaded_file_name,
                    config={
                        "display_name":f"audit_job_{chunk_id}"
                    }
                )
                logger.info(f"Successfully started job: {job.name}")
                return job

            except Exception as e:
                # check for 429 error specifically
                error_message = str(e)
                if "RESOURCE_EXHAUSTED" in error_message or "429" in error_message:
                    if attempt < self.max_retries - 1:
                        wait_time = 2 ** attempt  # exponential backoff: 1s, 2s, 4s, 8s...
                        logger.warning(f"429 RESOURCE_EXHAUSTED for Chunk {chunk_id}. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"Failed to submit batch job for Chunk {chunk_id} after {attempt + 1} attempts. Quota may be exceeded.")
                        raise e
                else:
                    logger.error(f"Failed to submit batch job for Chunk {chunk_id} due to unexpected error.")
                    raise e
        return job
                
    def handle_results(self, job, chunk_id: int):
            """Downloads, parses, and caches results from a completed batch job."""
            if not job.dest or not job.dest.file_name:
                logger.error(f"Job {job.name} succeeded but has no output file.")
                return

            logger.info(f"Downloading results for job {job.name}...")
            
            try:
                file_content = self.client.files.download(file=job.dest.file_name).decode('utf-8')
            except Exception as e:
                logger.error(f"Failed to download file {job.dest.file_name}: {e}")
                return

            success_count = 0
            
            for line in file_content.strip().split('\n'):
                if not line:
                    continue
                
                try:
                    batch_result = json.loads(line)
                    
                    # tweet ID is retrieved via the key we set
                    tweet_id = batch_result.get('key') 
                    if not tweet_id: continue

                    # extract the actual content from Gemini's response
                    response_part = batch_result['response']['candidates'][0]['content']['parts'][0]['text']
                    
                    # clean and parse the nested JSON
                    result = self._parse_analysis_response(response_part, tweet_id)
                    
                    if result:
                        self.cache.set(tweet_id=tweet_id, chunk_id=chunk_id, result=result) 
                        success_count += 1
                        
                except Exception as e:
                    logger.error(f"Error processing a result line: {e}")
                    logger.debug(f"Line content: {line[:100]}...")

            logger.info(f"Job {job.name} complete. Successfully cached {success_count} tweets.")

    def run_batch_pipeline(self, all_tweets: List[Dict], chunk_id: Optional[int]):
            """
            orchestrates the submission and monitoring of batch jobs.
            """
            
            if not self.client:
                 logger.error("Cannot run batch pipeline: Gemini Client not initialized.")
                 return
                 
            # filter tweets by chunk ID (if provided)
            if chunk_id is not None:
                tweets_for_processing = self.split_into_chunks(all_tweets, chunk_id)
                chunk_range = [chunk_id]
            else:
                # if no chunk_id provided, process all chunks serially
                tweets_for_processing = all_tweets
                chunk_range = range(NUMBER_OF_CHUNKS)

            # filter out already cached tweets
            tweets_to_process = []
            for t in tweets_for_processing:
                tweet_data = t.get("tweet", {})
                tweet_id = str(tweet_data.get("id_str") or tweet_data.get("id", "unknown"))

                if tweet_id != 'unknown' and not self.cache.get(tweet_id):
                    tweets_to_process.append(t)
            
            if not tweets_to_process:
                logger.info("All selected tweets are already cached!")
                return

            logger.info(f"Processing {len(tweets_to_process)} unique tweets via Batch API...")

            active_jobs = []

            if chunk_id is not None:
                chunks_to_submit = [tweets_to_process]
            else:
                # re-chunk
                chunks_to_submit = [
                    self.split_into_chunks(tweets_to_process, i)
                    for i in range(NUMBER_OF_CHUNKS)
                ]
                # filter out empty chunks and track their original ID
                chunks_to_submit = [(i, c) for i, c in enumerate(chunks_to_submit) if c]
                # unpack filtered list for iteration
                chunk_range = [i for i, c in chunks_to_submit]
                chunks_to_submit = [c for i, c in chunks_to_submit]
            
            for i, chunk in enumerate(chunks_to_submit):
                current_chunk_id = chunk_range[i] if chunk_id is None else chunk_id
                
                uploaded_file = self.create_batch_file(chunk, current_chunk_id)
                
                logger.info(f"Starting batch job for chunk {current_chunk_id}...")
                job = self._create_batch_job_with_retry(
                    uploaded_file_name=uploaded_file.name,
                    chunk_id=current_chunk_id
                )
                
                active_jobs.append({
                    "job_object": job,
                    "chunk_id": current_chunk_id,
                    "file_uri": uploaded_file.name
                })

            logger.info(f"Monitoring {len(active_jobs)} active jobs...")
            start_time = time.time()
            
            completed_states = {'JOB_STATE_SUCCEEDED', 'JOB_STATE_FAILED', 'JOB_STATE_CANCELLED'}
            
            while active_jobs: # while activate jobs is not empty
                for job_info in active_jobs[:]:
                    job_name = job_info['job_object'].name
                    chunk_id = job_info['chunk_id']
                    
                    # track job
                    current_job = self.client.batches.get(name=job_name)
                    state = current_job.state.name
                    logger.info(f"Current job state: {state}")
                    
                    if state in completed_states:
                        logger.info(f"Job {job_name} finished: {state}")
                        
                        if state == 'JOB_STATE_SUCCEEDED':
                            self.handle_results(current_job, chunk_id)
                        else:
                            logger.error(f"Job failed: {current_job.error}")
                        
                        # clean up the file in cloud storage
                        self.client.files.delete(name=job_info['file_uri'])
                        
                        # cleanup: remove from tracking list
                        active_jobs.remove(job_info)
                
                if active_jobs:
                    logger.info(f"Waiting 30s before next poll. {len(active_jobs)} jobs remaining...")
                    time.sleep(30)
            
            elapsed_time = start_time - time.time()
            logger.info(f"Batch took {elapsed_time} to finish")

    def generate_json_report(self, archive_data: str, output_filename: str, chunk_id: Optional[int] = None):
            """
            reads processed data from the cache and writes it to a JSON file.
            """
            if not self.cache.cache_dir.exists():
                logger.error(f"Cache directory not found: {self.cache.cache_dir}")
                return

            all_results = []
            logger.info("Aggregating results from cache files...")


            # look up tweet with corresponding tweet_id
            tweet = {}
            for tweets in archive_data:
                tweet_data = tweets.get("tweet", "")
                tweet_id = str(tweet_data.get("id", "") or tweet_data.get("id_str", ""))
                tweet_text = tweet_data.get("full_text", "")
                if tweet_id != 'unknown':
                    tweet[tweet_id] = tweet_text
            
            cache_files = list(self.cache.cache_dir.glob("*.pkl"))
            
            for file_path in tqdm(cache_files, desc="Reading Cache"):
                try:
                    # extracts tweet ID from filename
                    tweet_id = file_path.stem.replace("tweet_", "").replace(".pkl", "")
                    
                    with open(file_path, 'rb') as f:
                        analysis_data = pickle.load(f)

                        # filter for chunk_id
                        source_chunk_id = analysis_data.get('chunk_id')
                
                        if source_chunk_id is None:
                            # legacy File (No metadata)
                            source_chunk_id = -1 # sentinel value for unknown/legacy chunk
                            logger.debug(f"Assigned chunk_id -1 to legacy file {tweet_id}")
                        
                        if chunk_id is not None and source_chunk_id != chunk_id:
                            # filtering applied, and this item doesn't match
                            continue 

                    original_tweet = tweet.get(tweet_id)
                    
                    row = {
                        "tweet_id": tweet_id,
                        "chunk_id": source_chunk_id,
                        "original_tweet": original_tweet,
                        "reason_for_flag": analysis_data.get("reason_for_flag", "N/A"),
                        "explicit_words": analysis_data.get("explicit_words", []), 
                        "topic_of_tweet": analysis_data.get("topic_of_tweet", []), 
                    }
                    all_results.append(row)
                    
                except Exception as e:
                    logger.warning(f"Skipping failed cache file {file_path.name}: {e}")

            if not all_results:
                logger.info("No audit results found in cache to generate report.")
                return

            # determine output filename based on chunk ID
            if chunk_id is not None:
                base_name, ext = os.path.splitext(output_filename)
                if ext.lower() != '.json': # ensure correct extension if non-json
                     base_name = output_filename
                # append chunk ID to the filename
                output_filename = f"{base_name.replace('.json', '')}_chunk_{chunk_id}.json"
            elif os.path.splitext(output_filename)[1].lower() != '.json':
                 output_filename = os.path.splitext(output_filename)[0] + '.json'
                 
            output_path = Path(output_filename)
            output_path.parent.mkdir(exist_ok=True, parents=True)
            
            # write the data to the JSON file
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(all_results, f, indent=4, ensure_ascii=False)
                
                logger.info(f"Report generated successfully with {len(all_results)} entries: {output_path.resolve()}")
                
            except Exception as e:
                logger.error(f"Failed to write JSON file: {e}")


async def analyze_single_archive_tweet(input_path: str, output_path: str, chunk_id: Optional[int]):
    """
    orchestrates the entire Tweet Audit pipeline for a specific data chunk or all chunks.
    """
    logger.info(f"Starting analysis for Chunk ID: {chunk_id if chunk_id is not None else 'ALL'}")
    logger.info(f"Input file: {input_path}")
    logger.info(f"Report filename: {output_path}")
    
    try:
        auditor = AuditTweet()

        archive_data = auditor.read_archive_data(input_path)
        
        # run the batch pipeline (submits jobs for the target chunk ID or all)
        auditor.run_batch_pipeline(archive_data, chunk_id=chunk_id)
        
        logger.info("Batch analysis pipeline finished and results are cached.")

        # generate the final JSON report (passes chunk_id for chunked output naming)
        auditor.generate_json_report(archive_data=archive_data,output_filename=output_path, chunk_id=chunk_id)
        auditor.cache.get_stats()

        logger.info("Execution complete.")

    except Exception as e:
        logger.error(f"Critical failure in main execution: {e}")
        logger.debug(f"Exception: {traceback.format_exc()}")

if __name__ == "__main__":
    RUN_DEFAULTS = CONFIG.get("run_defaults", {})

    parser = argparse.ArgumentParser(
        description="Analyze tweet archive data using the Gemini Batch API.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument(
        '--file-path',
        type=str,
        required=False,
        default=RUN_DEFAULTS.get("file_path", None),
        help="Path to the input tweet archive file (e.g., 'data/tweets.js')."
    )
    
    parser.add_argument(
        '--output-path',
        type=str,
        required=False,
        default=RUN_DEFAULTS.get("output_path", None),
        help="The filename for the resulting JSON report (e.g., 'report_v1.json'). If running in chunked mode, the chunk ID will be appended."
    )

    parser.add_argument(
        '--chunk-id',
        type=int,
        default=RUN_DEFAULTS.get("chunk_id", None),
        help=f"Identifier for the specific chunk to process (0-indexed). Set between (0 <-> {NUMBER_OF_CHUNKS - 1}). If not set, all chunks are processed."
    )
    
    parser.add_argument(
        '--clear-cache', 
        action='store_true', 
        help="Clear the local cache before starting the analysis."
    )
    
    parser.add_argument(
        '--report-only', 
        action='store_true', 
        help=(
            "Skip the API processing stage and only generate the CSV report "
            "from existing data in the cache directory."
        )
    )

    args = parser.parse_args()

    if not args.file_path:
            logger.error("Error: --file-path is missing, and no default was found in config.json.")
            sys.exit(1)

    if args.chunk_id is not None and not (0 <= args.chunk_id < NUMBER_OF_CHUNKS):
        logger.error(f"Invalid chunk_id: {args.chunk_id}. Must be between 0 and {NUMBER_OF_CHUNKS - 1}")
        print(f"Error: --chunk-id must be an integer between 0 and {NUMBER_OF_CHUNKS - 1}.")
        sys.exit(1)

    config_clear_cache = RUN_DEFAULTS.get("clear_cache", False)
    config_report_only = RUN_DEFAULTS.get("report_only", False)

    try:
        temp_auditor = AuditTweet() 

        if config_clear_cache:
            logger.info(f"\n--- CACHE CLEARED: {CACHE_DIR} ---\n")
            temp_auditor.cache.clear()
            
        if config_report_only:
            print("\n--- REPORT ONLY MODE: Generating JSON from cache ---\n")
            # pass chunk-id to ensure correct chunk file naming
            temp_archive_data = temp_auditor.read_archive_data(args.file_path)
            temp_auditor.generate_json_report(
                archive_data=temp_archive_data,
                output_filename=args.output_path,
                chunk_id=args.chunk_id
            )
            sys.exit(0)
            
    except Exception as e:
        logger.error(f"Initialization failure: {e}")
        sys.exit(1)

    try:
        import asyncio
        asyncio.run(analyze_single_archive_tweet(
            input_path=args.file_path,
            output_path=args.output_path,
            chunk_id=args.chunk_id
        ))
    except Exception as e:
        logger.critical(f"Execution terminated unexpectedly: {e}")
        sys.exit(1)