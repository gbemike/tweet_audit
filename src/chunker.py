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
    
        filtered_chunk = []
        for tweet in tweets:
            tweet_id = self._get_tweet_id(tweet)
            if not tweet_id or tweet_id == "unknown":
                logger.warning(f"Tweet in chunk {chunk_id} has invalid ID, skipping")
                continue
            
            if not self.cache.exists(tweet_id):
                filtered_chunk.append(tweet)

        filtered_count = len(tweets) - len(filtered_chunk)
        if filtered_count > 0:
            logger.info(f"Chunk {chunk_id}: Filtered {filtered_count} cached tweets")
        
        return filtered_chunk


    def get_chunk(self, tweets: List[Dict], chunk_id: int) -> List[Dict]:
        if not (0 <= chunk_id < self.number_of_chunks):
            raise ValueError(f"chunk_id {chunk_id} out of range [0, {self.number_of_chunks})")
        
        chunk_data = [item for idx, item in enumerate(tweets) if idx % self.number_of_chunks == chunk_id]

        filtered_chunk = self._filter_cached(chunk_data, chunk_id)    
        logger.info(f"Chunk {chunk_id}: {len(filtered_chunk)} items to process")
        return filtered_chunk

    def get_all_chunks(self, tweets: List[Dict]) -> List[Dict]:
        chunks = [[] for _ in range(self.number_of_chunks)]
        for idx, item in enumerate(tweets):
            chunks[idx % self.number_of_chunks].append(item)
        
        result = []
        for chunk_id, chunk_data in enumerate(chunks):
            if not chunk_data:
                continue
            
            filtered_chunk = self._filter_cached(chunks, chunk_id)    
            
            if chunk_data:
                logger.info(f"Chunk {chunk_id}: {len(filtered_chunk)} items to process")
                result.append(filtered_chunk)
            else:
                logger.debug(f"Chunk {chunk_id}: empty after filtering, skipping")
        
        return result