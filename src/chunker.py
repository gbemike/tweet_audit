import logging
from typing import Dict, List, Optional

from cache import CacheManager
from config import AppConfig

logger = logging.getLogger(__name__)


class Chunker:
    def __init__(self, config: AppConfig, cache: Optional[CacheManager] = None):
        self.number_of_chunks = config.processing.number_of_chunks
        if self.number_of_chunks <= 0:
            raise ValueError("number_of_chunks must be > 0")
        self.cache = cache

    def _get_tweet_id(self, tweet: Dict) -> Optional[str]:
        tweet_data = tweet.get("tweet", {})
        tweet_id = tweet_data.get("id_str") or tweet_data.get("id")
        return str(tweet_id) if tweet_id else None

    def _filter_cached(self, tweets: List[Dict], chunk_id: int) -> List[Dict]:
        if not self.cache:
            return tweets
        
        cache_dir_exists = self.cache.cache_dir.is_dir()
        
        if not cache_dir_exists:
            logger.info(f"Chunk {chunk_id}: Cache directory {self.cache.cache_dir} not found. Processing all {len(tweets)} items.")
            return tweets
    
        uncached_chunk = []
        cached_chunk = []

        for tweet in tweets:
            tweet_id = self._get_tweet_id(tweet)
            if not tweet_id or tweet_id == "unknown":
                logger.warning(f"Tweet in chunk {chunk_id} has invalid ID, skipping")
                continue
            
            if not self.cache.exists(tweet_id):
                uncached_chunk.append(tweet) # fresh ids
            else:
                cached_chunk.append(tweet) # already cached ids

 
        logger.info(f"Chunk {chunk_id}: Got {len(uncached_chunk)} uncached tweets")
        logger.info(f"Chunk {chunk_id}: Got {len(cached_chunk)} cache tweets")

        return uncached_chunk, cached_chunk


    def get_uncached_chunk(self, tweets: List[Dict], chunk_id: int) -> List[Dict]:
        if not (0 <= chunk_id < self.number_of_chunks):
            raise ValueError(f"chunk_id {chunk_id} out of range [0, {self.number_of_chunks})")
        
        chunk_data = [item for idx, item in enumerate(tweets) if idx % self.number_of_chunks == chunk_id]

        uncached_chunk, cached_chunk = self._filter_cached(chunk_data, chunk_id)    
        return uncached_chunk, cached_chunk

    # def get_all_chunks(self, tweets: List[Dict], chunk_id: int) -> List[Dict]:
    #     if not (0 <= chunk_id < self.number_of_chunks):
    #         raise ValueError(f"chunk_id {chunk_id} out of range [0, {self.number_of_chunks})")
        
    #     chunk_data = [item for idx, item in enumerate(tweets) if idx % self.number_of_chunks == chunk_id]

    #     logger.info(f"Chunk {chunk_id}: {len(chunk_data)} items to process")
    #     return chunk_data
