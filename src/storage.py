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
        self.config = config
        self.data_path = Path(config.run_defaults.file_path)
        self.output_path = Path(config.run_defaults.output_path)

        self.output_path.mkdir(parents=True, exist_ok=True)

        self.number_of_chunks = config.processing.number_of_chunks

    def read_data(self) -> List[Dict]:
        if not self.data_path.exists():
            logger.error(f"Data file not found: {self.data_path}")
            raise FileNotFoundError(f"Data file not found: {self.data_path}")
        
        if self.data_path.suffix.lower() != ".js":
            logger.error(f"Invalid file type: Expected '.js' but found '{self.data_path.suffix}'")
            raise ValueError("Input data file must have a '.js' extension for custom parsing.")

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
        except json.JSONDecodeError as e:
                logger.error(f"Failed to decode JSON content extracted by regex: {e}")
                raise ValueError(f"Extracted content is not valid JSON: {e}")
        except Exception as e:
            logger.error(f"Failed to read data: {e}")
            raise

    def save_json(self, data: List[Dict], chunk_id: int) -> Path:
        filename = f"report_chunk_{chunk_id}.json"
        output_file = self.output_path / filename
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            if not data:
                logger.info(f"Empty JSON saved: {output_file.resolve()}")
            else:
                logger.info(f"JSON saved: {output_file.resolve()} ({len(data)} items)")
            
            return output_file
            
        except Exception as e:
            logger.error(f"Failed to save JSON to {output_file}: {e}")
            raise


    def save_csv(self, data: List[Dict], fieldnames: List[str], chunk_id: int) -> Path:
        filename = f"report_chunk_{chunk_id}.csv"
        output_file = self.output_path / filename
        
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(data)
            
            logger.info(f"CSV saved: {output_file.resolve()} ({len(data)} rows)")
            return output_file
            
        except Exception as e:
            logger.error(f"Failed to save CSV to {output_file}: {e}")
            raise

    def merge_chunks(self) -> None:
        pattern = self.config.processing.merge_pattern
        output_name = self.config.processing.merge_output_name
        chunk_files = sorted(self.output_path.glob(pattern))

        if not chunk_files:
            logger.error("No chunk files found to merge. Pipeline failed.")
            raise FileNotFoundError("No chunk files to merge")
        
        expected_chunks = self.number_of_chunks
        all_chunks_present = len(chunk_files) == expected_chunks

        if not all_chunks_present:
            logger.warning(
                f"Expected {expected_chunks} chunks, found {len(chunk_files)}. "
            )

        output_file = self.output_path / output_name
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as outfile:
                writer = None

                for idx, file in enumerate(chunk_files):
                    with open(file, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        if idx == 0:
                            writer = csv.DictWriter(outfile, fieldnames=reader.fieldnames, extrasaction="ignore")
                            writer.writeheader()
                        for row in reader:
                            writer.writerow(row)
                    logger.info(f"Merged {file.name}")

            logger.info(f"{len(chunk_files)} chunks merged to: {output_file.resolve()}")

            return output_file
        
        except Exception as e:
            logger.error(f"Failed to merge chunks: {e}")
            raise
        
    def save_failed_ids(self, failed_ids: List[str], chunk_id: int) -> Optional[Path]:
        if not failed_ids:
            logger.info(f"No failed IDs to save for chunk {chunk_id}")
            filename_json = f"failed_ids_chunk_{chunk_id}.json"
            output_json = self.output_path / filename_json
            try:
                with open(output_json, "w", encoding="utf-8") as f:
                    json.dump([], f, ensure_ascii=False, indent=2)
                logger.info(f"Empty failed-ids file created: {output_json.resolve()}")
                return output_json
            except Exception as e:
                logger.error(f"Failed to write empty failed-ids file for chunk {chunk_id}: {e}")
                return None

        filename_json = f"failed_ids_chunk_{chunk_id}.json"
        output_json = self.output_path / filename_json

        try:
            with open(output_json, "w", encoding="utf-8") as jf:
                json.dump(failed_ids, jf, ensure_ascii=False, indent=2)

            logger.info(f"Saved {len(failed_ids)} failed IDs for chunk {chunk_id}: {output_json.resolve()}")
            return output_json

        except Exception as e:
            logger.error(f"Failed to save failed IDs for chunk {chunk_id}: {e}")
            raise