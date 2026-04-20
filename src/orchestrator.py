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
        self.batch_manager = BatchManager(config=self.config, storage=self.storage, cache=self.cache)

        self.fieldnames = self.config.processing.default_csv_fields
        
    def run(self, tweets: List[Dict], chunk_id: int):
        try:
            # gets uncached chunks
            uncached_tweets, cached_tweets = self.chunker.get_uncached_chunk(tweets, chunk_id)
            
            if not uncached_tweets:
                logger.info(f"Chunk {chunk_id}: No tweets to process (all cached)")
                return

            if cached_tweets:
                logger.info(f"Chunk {chunk_id}: {len(cached_tweets)} tweets left to process")
            
            logger.info(f"Processing chunk {chunk_id} with {len(uncached_tweets)} tweets")
            self._process_single_chunk(chunk_id, uncached_tweets, cached_tweets)
            logger.info(f"Chunk {chunk_id}: Complete")
            
        except Exception as e:
            logger.error(f"Chunk {chunk_id}: FAILED - {e}", exc_info=True)
            sys.exit(1)

    def _process_single_chunk(self, chunk_id: int, uncached_tweets: List[Dict], cached_tweets: List[Dict]):
        logger.info(f"Chunk {chunk_id}: Running batch pipeline for {len(uncached_tweets)} tweets...")
        logger.info(f"Chunk {chunk_id}: {len(cached_tweets)} previously cached tweets")

        try:
            processed_tweets = self.batch_manager.run_batch_pipeline(uncached_tweets, chunk_id)
        except Exception as e:
            logger.error(f"Chunk {chunk_id}: Batch pipeline failed - {e}", exc_info=True)
            raise

        if not processed_tweets:
            logger.warning(f"Chunk {chunk_id}: No results from batch pipeline")
            processed_tweets = []

        expected = len(cached_tweets) + len(uncached_tweets)

        # merge new and old results
        merged_tweets = self._merge_old_and_new_tweets(processed_tweets, cached_tweets, chunk_id)

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


    def _merge_old_and_new_tweets(self, processed_tweets: List[Dict], cached_tweets: List[Dict], chunk_id: int) -> List[Dict]:
        seen_ids = set()
        merged_results = []

        # get old results
        cached_tweet_results = []

        if self.cache:
            for tweet in cached_tweets:
                tweet_data = tweet.get("tweet")
                tweet_id = tweet_data.get("id_str") or tweet_data.get("id")
                cache_data = self.cache.get(tweet_id)
                cached_tweet_results.append(cache_data)

        # old tweets + new tweets
        all_tweets = processed_tweets + cached_tweet_results

        for tweet in all_tweets:
            tweet_id = str(tweet.get("tweet_id", ""))
            if tweet_id and tweet_id in seen_ids:
                continue
            if tweet_id:
                seen_ids.add(tweet_id)

            merged_results.append(tweet)

        logger.info(f"Chunk {chunk_id}: Merged {len(cached_tweet_results)} cached + {len(processed_tweets)} new = {len(merged_results)} total")

        return merged_results