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
                f"Partial merge — chunk files will be kept for next run."
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
            
            if all_chunks_present:
                for file in chunk_files:
                    file.unlink()
                    logger.info("Cleaned up chunk files")
            else:
                logger.warning(
                    f"Keeping chunk files — only {len(chunk_files)} / {expected_chunks} chunks present. "
                    f"Re-run pipeline to complete missing chunks."
                )

            return output_file
        
        except Exception as e:
            logger.error(f"Failed to merge chunks: {e}")
            raise