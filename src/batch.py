import json
import logging
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

from google import genai
from google.genai import types
from google.genai.errors import APIError 

from cache import CacheManager
from storage import Storage
from config import AppConfig

logger = logging.getLogger(__name__)

class BatchManager:
    def __init__(self, config: AppConfig, storage: Storage, cache: Optional[CacheManager] = None):
        self.config = config
        self.cache = cache
        self.storage = storage
        
        self.batch_path = Path(config.batch_files.directory)
        self.criteria = self.config.criteria
        self.model = self.config.model.primary
        self.max_retries = self.config.model.max_retries
        self.job_timeout = self.config.model.job_timeout
        self.user = self.config.url_builder.user
        self.base_url = self.config.url_builder.base_url

        self.batch_path.mkdir(parents=True, exist_ok=True)

        self.client = genai.Client()

    def _create_prompt(self, tweet_text: str) -> str:
        criteria_str = (
            f"Forbidden words: {', '.join(self.criteria.forbidden_words)}\n"
            f"Topics to exclude: {', '.join(self.criteria.topics_to_exclude)}\n"
            f"Tone requirements: {', '.join(self.criteria.tone_requirements)}\n"
            f"Additional instructions: {self.criteria.additional_instructions}"
        )
        return f"""
        Analyze this tweet and determine if it should be flagged for deletion.

        Tweet: "{tweet_text}"

        Criteria for flagging
        {criteria_str}

        CRITICAL INSTRUCTIONS:
        1. Respond ONLY with valid JSON - no markdown, no code blocks, no explanations
        2. Do NOT wrap your response in ```json or ``` tags
        3. Use double quotes for all strings
        4. Ensure "deletion" is EXACTLY either "DELETE" or "KEEP" (all caps)
        5. If no explicit words found, use empty array []
        6. All arrays must be properly formatted


        Example of VALID response:
        {{
        "explicit_words": ["damn"],
        "reason_for_flag": "Contains mild profanity",
        "topic_of_tweet": ["complaint", "frustration"],
        "deletion": "DELETE"
        }}

        Example of VALID response (no issues):
        {{
        "explicit_words": [],
        "reason_for_flag": "Tweet is clean and appropriate",
        "topic_of_tweet": ["technology", "news"],
        "deletion": "KEEP"
        }}

        Now analyze the tweet above and respond with ONLY the JSON object
        """

    def _parse_response(self, response_text: str, tweet_id: str, tweet_url: str) -> Optional[Dict]:
        cleaned_text = response_text.strip().replace("```json", "").replace("```", "")

        try:
            match = re.search(r"\{.*\}", cleaned_text, re.DOTALL)
            if match:
                json_str = match.group(0)
            else:
                json_str = cleaned_text
            data = json.loads(json_str)

            required_keys = ["explicit_words", "reason_for_flag", "topic_of_tweet", "deletion"]
            if not all(k in data for k in required_keys):
                logger.warning(f"Tweet {tweet_id}: Missing required keys. Found: {list(data.keys())}")
                return None
            return data

        except json.JSONDecodeError as e:
            logger.error(f"Tweet {tweet_id}: Failed to parse JSON. Error: {e}")
            logger.debug(f"Raw content: {response_text}")
            return None
        except Exception as e:
            logger.error(f"Tweet {tweet_id}: Unexpected error parsing response: {e}")
            return None

    def create_batch_file(self, tweets: List[Dict], chunk_id: int) -> types.File:
        batch_file_path = self.batch_path / f"batch_chunk_{chunk_id}.jsonl"
        logger.info(f"[Chunk {chunk_id}] Creating batch file for {len(tweets)} tweets")

        try:
            with open(batch_file_path, "w", encoding="utf-8") as f:
                for tweet in tweets:
                    tweet_data = tweet.get("tweet", {})
                    tweet_id = str(tweet_data.get("id_str") or tweet_data.get("id", "unknown"))
                    tweet_text = tweet_data.get("full_text", "")

                    request_obj = {
                        "key": tweet_id,
                        # "tweet_id": tweet_id,
                        "tweet_url": self.base_url.format(user=self.user, id=tweet_id),
                        "request": {
                            "contents": [{
                                "parts": [{
                                    "text": self._create_prompt(tweet_text)
                                }]
                            }]
                        }
                    }
                    f.write(json.dumps(request_obj, ensure_ascii=False) + "\n")
        except IOError as e:
            logger.error(f"[Chunk {chunk_id}] Failed to write local batch file {batch_file_path}: {e}")
            raise

        logger.info(f"[Chunk {chunk_id}] Local batch file created: {batch_file_path.resolve()}")

        try:
            uploaded_file = self.client.files.upload(
                file=batch_file_path,
                config=types.UploadFileConfig(display_name=f"audit_chunk_{chunk_id}", mime_type="jsonl")
            )
        except APIError as e:
            logger.error(f"[Chunk {chunk_id}] API failed to upload file {batch_file_path}. Details: {e}")
            raise
        except Exception as e:
            logger.error(f"[Chunk {chunk_id}] Unexpected error during file upload: {e}")
            raise

        logger.info(f"[Chunk {chunk_id}] Uploaded file: {uploaded_file.name}")
        return uploaded_file

    def _submit_batch_with_retry(self, uploaded_file_name: str, chunk_id: int) -> types.BatchJob:
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Submitting batch job for chunk {chunk_id}, attempt {attempt + 1}")
                job = self.client.batches.create(model=self.model, src=uploaded_file_name,
                                                 config={"display_name": f"audit_job_{chunk_id}"})
                logger.info(f"Job started: {job.name}")
                return job
            except Exception as e:
                if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                    wait_time = 2 ** attempt
                    logger.warning(f"429 error, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                raise e

    def _poll_job_until_complete(self, job: types.BatchJob) -> types.BatchJob:
        if job is None:
            raise ValueError("Cannot poll job: Batch job object is None due to prior submission failure.")
        
        completed_states = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED"}
        start_time = time.time()

        while True:
            if time.time() - start_time > self.job_timeout:
                logger.error(f"Job {job.name} timed out after {self.job_timeout} seconds while polling.")
                raise TimeoutError(f"Batch job {job.name} exceeded maximum polling time.")
            
            try:
                current_job = self.client.batches.get(name=job.name)
                state = current_job.state.name
                logger.info(f"Job {job.name} state: {state}")

                if state in completed_states:
                    return current_job
            except APIError as e:
                logger.warning(f"API Error while polling job {job.name}. Retrying in 30s. Error: {e}")

            time.sleep(300)

    def handle_results(self, job: types.BatchJob) -> List[Dict]:
        if not job.dest or not job.dest.file_name:
            logger.error(f"Job {job.name} has no output file")
            return

        logger.info(f"Downloading results for job {job.name}...")

        try:
            file_content = self.client.files.download(file=job.dest.file_name).decode("utf-8")
        except APIError as e:
            logger.error(f"API failed to download results for job {job.name}. Details: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during results download for job {job.name}: {e}")
            raise

        parsed_results = []
        failed_count = 0
        failed_ids = []
        
        for line_num, raw_line in enumerate(file_content.strip().split("\n"), 1):
            if not raw_line:
                logger.warning(f"Line {line_num}: Empty line, skipping")
                continue
        
            try:
                obj = json.loads(raw_line)
            except json.JSONDecodeError:
                logger.error(f"Line {line_num}: Malformed JSON, skipping")
                failed_count += 1
                continue
        
            if not isinstance(obj, dict) or "key" not in obj:
                logger.error(f"Line {line_num}: Invalid structure, skipping")
                failed_count += 1
                continue
        
            tweet_id = obj.get("key") # this is the tweet_id
            tweet_url = obj.get("tweet_url", "")

            try:
                response_obj = obj["response"]
                text = response_obj["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError, TypeError) as e:
                logger.error(f"Line {line_num} (tweet {tweet_id}): Could not extract response text: {e}")
                failed_count += 1
                failed_ids.append(tweet_id)
                continue
        
            parsed = self._parse_response(text, tweet_id, tweet_url)
            if not parsed:
                logger.error(f"Line {line_num} (tweet {tweet_id}): Failed to parse/validate response")
                failed_count += 1
                failed_ids.append(tweet_id)
                continue
            
            parsed["tweet_id"] = tweet_id
            parsed["tweet_url"] = tweet_url

            if self.cache.set(tweet_id, parsed):
                logger.debug(f"Cached result for tweet {tweet_id}")

            parsed_results.append(parsed)
        
        success_count = len(parsed_results)
        total_count = success_count + failed_count
        
        logger.info(
            f"Job {job.name} results: {success_count} out of {total_count} jobs successful"
        )
        
        if failed_count > 0:
            logger.warning(f"{failed_count} tweets failed parsing/validation!!")
        
        return parsed_results, failed_ids

    def run_batch_pipeline(self, tweets: List[Dict], chunk_id: int) -> List[Dict]:
        if not tweets:
            logger.info(f"Chunk {chunk_id}: No tweets to process")
            return []

        uploaded_file = self.create_batch_file(tweets, chunk_id)
        job = self._submit_batch_with_retry(uploaded_file_name=uploaded_file.name, chunk_id=chunk_id)

        completed_job = self._poll_job_until_complete(job)

        if completed_job.state.name != "JOB_STATE_SUCCEEDED":
            logger.error(f"Job {job.name} did not succeed: {completed_job.state.name}")
            if hasattr(completed_job, 'error'):
                logger.error(f"Error details: {completed_job.error}")
            return []
        
        results, failed_ids = self.handle_results(completed_job)

        self.storage.save_failed_ids(failed_ids, chunk_id)

        return results
