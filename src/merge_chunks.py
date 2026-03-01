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
    config = load_config(CONFIG_PATH)
    cache = CacheManager(config)
    try:
        storage = Storage(config)
        
        logger.info("Starting merge process...")
        storage.merge_chunks()
        logger.info("Merge complete")
        
    except Exception as e:
        logger.error(f"Merge failed: {e}", exc_info=True)
        exit(1)
    finally:
        cache.release_lock()

if __name__ == "__main__":
    main()