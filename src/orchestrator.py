import logging
from typing import Dict, List
import sys

from batch import BatchManager
from cache import CacheManager
from chunker import Chunker
from config import AppConfig
from storage import Storage

logger = logging.getLogger(__name__)

class Orchestrator:
    def __init__(self, config: AppConfig, storage: Storage, cache: CacheManager = None):
        self.config = config
        self.cache = cache
        self.storage = storage
        self.chunker = Chunker(config=self.config, cache=self.cache)
        self.batch_manager = BatchManager(config=self.config, cache=self.cache)

        self.fieldnames = self.config.processing.default_csv_fields
        
    def run(self, tweets: List[Dict], chunk_id: int):
        try:
            chunk_data = self.chunker.get_chunk(tweets, chunk_id)
            all_chunk_data = self.chunker.get_all_chunks(tweets, chunk_id)
            
            if not chunk_data:
                logger.info(f"Chunk {chunk_id}: No tweets to process (all cached)")
                return
            
            logger.info(f"Processing chunk {chunk_id} with {len(chunk_data)} tweets")
            self._process_single_chunk(chunk_id, chunk_data, all_chunk_data)
            logger.info(f"Chunk {chunk_id}: Complete")
            
        except Exception as e:
            logger.error(f"Chunk {chunk_id}: FAILED - {e}", exc_info=True)
            sys.exit(1)

    def _process_single_chunk(self, chunk_id: int, tweets: List[Dict], all_chunk_tweets: List[Dict]):
        logger.info(f"Chunk {chunk_id}: Running batch pipeline for {len(tweets)} tweets...")

        cached_tweets = self.cache.filter_cache_chunks(all_chunk_tweets)
        logger.info(f"Chunk {chunk_id}: {len(cached_tweets)} previously cached tweets")

        try:
            uncached_tweets = self.batch_manager.run_batch_pipeline(tweets, chunk_id)
        except Exception as e:
            logger.error(f"Chunk {chunk_id}: Batch pipeline failed - {e}", exc_info=True)
            raise

        if not uncached_tweets:
            logger.warning(f"Chunk {chunk_id}: No results from batch pipeline")
            uncached_tweets = []

        expected = len(all_chunk_tweets)

        merged_tweets = self._merge_old_and_new_tweets(cached_tweets, uncached_tweets, chunk_id)

        if len(merged_tweets) != expected:
            logger.warning(
                f"Chunk {chunk_id}: Expected {expected} results, got {len(merged_tweets)}."
                f"{expected - len(merged_tweets)} tweets still missing."
            )
        else:
            logger.info(f"Chunk {chunk_id}: All {expected} tweets accounted for")
        
        csv_data = [
        {"tweet_url": row["tweet_url"], "deletion": row["deletion"]}
        for row in merged_tweets
        if row.get("deletion") != "N/A" and row.get("tweet_url")
        ]

        logger.info(f"Chunk {chunk_id}: Saving {len(merged_tweets)} results...")
    
        self.storage.save_json(data=merged_tweets, chunk_id=chunk_id)
        self.storage.save_csv(data=csv_data, fieldnames=self.fieldnames, chunk_id=chunk_id)
 
        logger.info(f"Chunk {chunk_id}: {len(merged_tweets)} tweets processed and saved")


    def _merge_old_and_new_tweets(self, cached_tweets: List[Dict], uncached_tweets: List[Dict], chunk_id: int) -> List[Dict]:
        seen_ids = set()
        merged_results = []

        all_tweets = uncached_tweets + cached_tweets

        for tweet in all_tweets:
            tweet_id = str(tweet.get("tweet_id", ""))
            if tweet_id and tweet_id in seen_ids:
                continue
            if tweet_id:
                seen_ids.add(tweet_id)

            merged_results.append(tweet)

        logger.info(f"Chunk {chunk_id}: Merged {len(cached_tweets)} cached + {len(uncached_tweets)} new = {len(merged_results)} total")

        return merged_results