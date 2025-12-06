#!/usr/bin/env python3
import logging
from config import load_config, get_config_path
from storage import Storage
from cache import CacheManager


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    try:
        config_path = get_config_path()
        config = load_config(config_path)
        
        storage = Storage(config)
        
        logger.info("Starting merge process...")
        storage.merge_chunks()
        logger.info("Merge complete")
        
        # release cache lock after successful merge
        if config.cache.enabled:
            cache = CacheManager(config)
            cache.release_lock()
        
    except Exception as e:
        logger.error(f"Merge failed: {e}", exc_info=True)
        
        # release lock on failure
        try:
            if config.cache.enabled:
                cache = CacheManager(config)
                cache.release_lock()
        except:
            pass
        
        exit(1)

if __name__ == "__main__":
    main()