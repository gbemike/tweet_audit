import logging
import os
from dotenv import load_dotenv

from cache import CacheManager
from config import load_config
from storage import Storage

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

CONFIG_PATH = os.getenv("CONFIG_PATH")

def main():
    try:
        config = load_config(CONFIG_PATH)
        
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