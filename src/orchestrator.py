import logging
from typing import Dict, List, Optional

from batch import BatchManager
from cache import CacheManager
from chunker import Chunker
from config import AppConfig
from storage import Storage

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, config: AppConfig, storage: Storage, cache: Optional[CacheManager] = None):
        self.config = config
        self.cache = cache
        self.storage = storage
        self.chunker = Chunker(config=config, cache=cache)
        self.batch_manager = BatchManager(config=config, cache=cache)
        
        self.json_filename = config.processing.default_json_filename
        self.csv_filename = config.processing.default_csv_filename
        self.fieldnames = config.processing.default_csv_fields
        
        logger.info("Orchestrator initialized")

    def run(self, tweets: List[Dict], chunk_id: Optional[int] = None):        
        if chunk_id is not None:
            chunk_data = self.chunker.get_chunk(tweets, chunk_id)
            logger.info(f"Processing only chunk {chunk_id}")
            self._process_single_chunk(chunk_id, chunk_data)
            return
        
        chunks = self.chunker.get_all_chunks(tweets)
        
        if not chunks:
            logger.warning("No chunks to process (all tweets cached)")
            return
        
        for chunk_id, chunk_data in chunks:
            logger.info(f"Processing chunk {chunk_id}")
            self._process_single_chunk(chunk_id, chunk_data)
        
        logger.info("All chunks processed, merging results...")
        self.storage.merge_chunks()
        logger.info("Pipeline complete")

    def _process_single_chunk(self, chunk_id: int, tweets: List[Dict]):
        if not tweets:
            logger.info(f"Chunk {chunk_id}: no tweets to process")
            return

        logger.info(f"Chunk {chunk_id}: Running batch pipeline for {len(tweets)} tweets...")
        results = self.batch_manager.run_batch_pipeline(tweets, chunk_id)

        if not results:
            logger.warning(f"Chunk {chunk_id}: No results returned from batch pipeline")
            return

        logger.info(f"Chunk {chunk_id}: Saving {len(results)} results...")
        
        self.storage.save_json(data=results, filename=self.json_filename, chunk_id=chunk_id)
        self.storage.save_csv(data=results, fieldnames=self.fieldnames, filename=self.csv_filename, chunk_id=chunk_id)

        logger.info(f"Chunk {chunk_id}: {len(results)} tweets flagged")