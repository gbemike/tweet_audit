import os
import sys
import csv
from pathlib import Path
from dotenv import load_dotenv
import json

load_dotenv()

CONFIG_PATH = os.getenv("CONFIG_PATH")

try:
    with open(CONFIG_PATH, "r") as f:
        CONFIG = json.load(f)
except FileNotFoundError:
    print("Error: config.json not found. Please create one.")
    sys.exit(1)


def merge_csv_chunks(chunk_path: str, output_name: str = 'merged_output.csv'):
    """Merge CSV chunk files into a single CSV file."""
    base_path = Path(chunk_path)
    chunk_files = sorted(list(base_path.glob('*_chunk_*.csv')))
    
    if not chunk_files:
        print(f"Error: No chunk files found in {chunk_path}")
        return
    
    output_path = base_path / output_name
    print(f"Found {len(chunk_files)} chunk files to merge.")
    
    try:
        with open(chunk_files[0], 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            
            if not headers:
                print(f"Error: First chunk file has no headers")
                return
            
            with open(output_path, 'w', newline='', encoding='utf-8') as outfile:
                writer = csv.DictWriter(outfile, fieldnames=headers)
                writer.writeheader()
                
                for row in reader:
                    writer.writerow(row)
                
                for chunk_file in chunk_files[1:]:
                    try:
                        with open(chunk_file, 'r', encoding='utf-8') as cf:
                            chunk_reader = csv.DictReader(cf)
                            
                            if chunk_reader.fieldnames != headers:
                                print(f"Warning: Header mismatch in {chunk_file.name}. Skipping.")
                                continue
                            
                            for row in chunk_reader:
                                writer.writerow(row)
                            
                            print(f"Merged {chunk_file.name}")
                    
                    except Exception as e:
                        print(f"Error processing {chunk_file.name}: {e}")
        
        print(f"Successfully merged to: {output_path.resolve()}")
    
    except Exception as e:
        print(f"Error during merge: {e}")


if __name__ == '__main__':
    merge_csv_chunks(chunk_path=CONFIG["run_defaults"]["output_path"])