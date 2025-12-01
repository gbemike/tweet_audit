import csv
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

from config import AppConfig

logger = logging.getLogger(__name__)

class Storage:
    def __init__(self, config: AppConfig):
        self.data_path = Path(config.run_defaults.file_path)
        self.output_path = Path(config.run_defaults.output_path)

        self.output_path.mkdir(parents=True, exist_ok=True)

    def read_data(self) -> List[Dict]:
        if not self.data_path.exists():
            logger.error(f"Data file not found: {self.data_path}")
            raise FileNotFoundError(f"Data file not found: {self.data_path}")

        try:
            with open(self.data_path, 'r', encoding='utf-8') as f:
                content = f.read()
            match = re.search(r"\[\s*{.*}\s*\]", content, flags=re.DOTALL)
            if not match:
                raise ValueError("No JSON array found")
            json_array_str = match.group(0)
            data = json.loads(json_array_str)
            logger.info(f"Loaded {len(data)} items from {self.data_path}")
            return data
        except Exception as e:
            logger.error(f"Failed to read data: {e}")
            raise

    def save_json(self, data: List[Dict], filename: str = None, chunk_id: int = None) -> Optional[Path]:
        if not data:
            logger.warning("No data to save.")
            return None

        if chunk_id is not None:
            filename = f"report_chunk_{chunk_id}.json"

        output_file = self.output_path / filename
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logger.info(f"JSON saved: {output_file.resolve()}")
        return output_file

    def save_csv(self, data: List[Dict], fieldnames: List[str], filename: str = None, chunk_id: int = None) -> Optional[Path]:
        if not data:
            logger.warning("No data to save.")
            return None

        if chunk_id is not None:
            filename = f"report_chunk_{chunk_id}.csv"

        output_file = self.output_path / filename
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in data:
                    deletion = row.get("deletion", "N/A")
                    tweet_url = row.get("tweet_url", "")
                    if deletion != "N/A" and tweet_url != "":
                        writer.writerow({
                            "tweet_url": tweet_url,
                            "deletion": deletion
                        })
                    
            logger.info(f"CSV saved: {output_file.resolve()}")
        except Exception as e:
            logger.error(f"Failed to save data to CSV {output_file}")
        return output_file


    def merge_chunks(self, pattern: str = "*_chunk_*.csv", output_name: str = "merged_report.csv") -> Optional[Path]:
        chunk_files = sorted(self.output_path.glob(pattern))

        if not chunk_files:
            logger.warning("No chunk files found to merge.")
            return

        output_file = self.output_path / output_name
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as outfile:
                writer = None

                for idx, file in enumerate(chunk_files):
                    with open(file, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        if idx == 0:
                            # write headers
                            writer = csv.DictWriter(outfile, fieldnames=reader.fieldnames)
                            writer.writeheader()
                        for row in reader:
                            writer.writerow(row)
                    logger.info(f"Merged {file.name}")

            logger.info(f"All chunks merged to: {output_file.resolve()}")
            return output_file
        
        except Exception as e:
            logger.error(f"Failed to merge chunks: {e}")
            raise
