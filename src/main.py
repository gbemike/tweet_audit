import argparse
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
    parser = argparse.ArgumentParser(description="Run the Tweet Audit Pipeline in chunks.")
    parser.add_argument(
        "--chunk-id", 
        type=int, 
        help="Specify the chunk ID to process for parallel execution (0 to N-1)."
    )
    args = parser.parse_args()

    start_time = time.time()
    if not CONFIG_PATH:
        logger.error("CONFIG_PATH environment variable is not set. Please set CONFIG_PATH to a valid configuration file path before running the pipeline.")
        raise SystemExit(1)
        
    logger.info("Loading configuration...")
    config = load_config(CONFIG_PATH)
    cache = CacheManager(config)

    logger.info("Checking cache configurations ...")
    if config.run_defaults.clear_cache:
        cache.clear()

    logger.info("Initializing storage...")
    storage = Storage(config)

    logger.info("Loading tweets...")
    tweets = storage.read_data()

    orchestrator = Orchestrator(config, storage, cache)

    logger.info("Starting orchestrator...")
    orchestrator.run(
        tweets,
        chunk_id=args.chunk_id
    )

    elapsed_time = time.time() - start_time
    logger.info(f"Pipeline completed successfully in {elapsed_time:.2f} seconds.")


if __name__ == "__main__":
    main()
