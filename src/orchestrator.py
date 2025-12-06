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
            
            if not chunk_data:
                logger.info(f"Chunk {chunk_id}: No tweets to process (all cached)")
                self.storage.save_json(data=[], chunk_id=chunk_id)
                self.storage.save_csv(data=[], fieldnames=self.fieldnames, chunk_id=chunk_id)
                return
            
            logger.info(f"Processing chunk {chunk_id} with {len(chunk_data)} tweets")
            self._process_single_chunk(chunk_id, chunk_data)
            logger.info(f"Chunk {chunk_id}: Complete")
            
        except Exception as e:
            logger.error(f"Chunk {chunk_id}: FAILED - {e}", exc_info=True)
            sys.exit(1)

    def _process_single_chunk(self, chunk_id: int, tweets: List[Dict]):
        logger.info(f"Chunk {chunk_id}: Running batch pipeline for {len(tweets)} tweets...")
        
        try:
            results = self.batch_manager.run_batch_pipeline(tweets, chunk_id)
        except Exception as e:
            logger.error(f"Chunk {chunk_id}: Batch pipeline failed - {e}", exc_info=True)
            raise

        if not results:
            logger.warning(f"Chunk {chunk_id}: No results from batch pipeline")
            self.storage.save_json(data=[], chunk_id=chunk_id)
            self.storage.save_csv(data=[], fieldnames=self.fieldnames, chunk_id=chunk_id)
            return
        
        csv_data = [
        {"tweet_url": row["tweet_url"], "deletion": row["deletion"]}
        for row in results
        if row.get("deletion") != "N/A" and row.get("tweet_url")
        ]

        logger.info(f"Chunk {chunk_id}: Saving {len(results)} results...")
        
        try:
            self.storage.save_json(data=results, chunk_id=chunk_id)
            self.storage.save_csv(data=csv_data, fieldnames=self.fieldnames, chunk_id=chunk_id)
        except Exception as e:
            logger.error(f"Chunk {chunk_id}: Failed to save results - {e}", exc_info=True)
            raise

        logger.info(f"Chunk {chunk_id}: {len(results)} tweets processed and saved")