import logging
import pickle
from pathlib import Path
from typing import Dict

from config import AppConfig

logger = logging.getLogger(__name__)

class CacheManager:
    def __init__(self, config: AppConfig):
        cache_cfg = config.cache
        
        self.enabled = cache_cfg.enabled
        self.cache_dir = Path(cache_cfg.directory)

        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, tweet_id: str) -> Path:
        safe_id = str(tweet_id).strip()
        return self.cache_dir / f"tweet_{safe_id}.pkl"
    
    def exists(self, tweet_id: str) -> bool:
        if not self.enabled:
            return False
        return self._get_file_path(tweet_id).exists()
    
    def get(self, tweet_id: str):
        cache_file = self._get_file_path(tweet_id)

        if not cache_file.exists():
            logger.debug(f"Cache MISS for {tweet_id}")
            return None
        
        try:
            with open(cache_file, 'rb') as f:
                cached_data = pickle.load(f)
                logger.debug(f"Cache HIT for {tweet_id}")
                return cached_data
        except Exception as e:
            logger.warning(f"Failed to load cache for {tweet_id}: {e}. Deleting file.")
            cache_file.unlink(missing_ok=True)
            return None

    def set(self, tweet_id: str, data: Dict):
        if not self.enabled:
            logger.debug(f"Cache is disabled can't save")
            return False
        
        try:
            with open(self._get_file_path(tweet_id), 'wb') as f:
                pickle.dump(data, f)
            return True
        except Exception as e:
            logger.warning(f"Failed to write cache for {tweet_id}: {e}")

    def clear(self):
        if not self.enabled:
            logger.debug(f"Cache is disabled can't clear")
            return None
        cleared = 0
        for files in self.cache_dir.glob("*.pkl"):
            try:
                files.unlink()
                cleared += 1
            except Exception as e:
                logger.error(f"Failed to delete {files}: {e}")
        logger.info(f"Cleared {cleared} cached files")
            
    def get_stats(self) -> dict:
        if not self.cache_dir.exists():
            return {'enabled': self.enabled, 'exists': False, 'total_entries': 0}

        files = list(self.cache_dir.glob("*.pkl"))
        total_size = sum(f.stat().st_size for f in files)
        stats = {
            'enabled': self.enabled,
            'exists': True,
            'total_entries': len(files),
            'total_size_bytes': total_size,
            'total_size_kb': round(total_size / 1024, 2),
        }
        logger.info(f"Cache stats: {stats}")
        return stats
    