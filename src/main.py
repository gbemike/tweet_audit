import logging
import os
import time

from dotenv import load_dotenv

from cache import CacheManager
from config import load_config
from orchestrator import Orchestrator
from storage import Storage

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

CONFIG_PATH = os.getenv("CONFIG_PATH")

def main():
    start_time = time.time()
    logger.info("Loading configuration...")
    config = load_config(CONFIG_PATH)
    cache = CacheManager(config)

    logger.info("Initializing storage...")
    storage = Storage(config)

    logger.info("Loading tweets...")
    tweets = storage.read_data()

    orchestrator = Orchestrator(config, storage, cache)

    logger.info("Starting orchestrator...")
    orchestrator.run(
        tweets,
        chunk_id=config.run_defaults.chunk_id
    )

    elapsed_time = time.time() - start_time
    logger.info(f"Pipeline completed successfully in {elapsed_time:.2f} seconds.")


if __name__ == "__main__":
    main()
