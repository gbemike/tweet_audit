import json
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class CriteriaConfig:
    forbidden_words: List[str]
    topics_to_exclude: List[str]
    tone_requirements: List[str]
    additional_instructions: str


@dataclass(frozen=True)
class CacheConfig:
    directory: str
    enabled: bool


@dataclass(frozen=True)
class ProcessingConfig:
    number_of_chunks: int
    default_csv_fields: List[str]
    default_csv_filename: str
    default_json_filename: str


@dataclass(frozen=True)
class ModelConfig:
    primary: str
    secondary: str
    max_retries: int


@dataclass(frozen=True)
class BatchFilesConfig:
    directory: str


@dataclass(frozen=True)
class RunDefaultsConfig:
    file_path: str
    output_path: str
    report_path: str
    chunk_id: int
    clear_cache: bool

@dataclass(frozen=True)
class UrlBuilder:
    user: str
    base_url: str

@dataclass(frozen=True)
class AppConfig:
    criteria: CriteriaConfig
    cache: CacheConfig
    processing: ProcessingConfig
    model: ModelConfig
    batch_files: BatchFilesConfig
    run_defaults: RunDefaultsConfig
    url_builder: UrlBuilder


def load_config(path: str | Path) -> AppConfig:
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file not found: {path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in config file: {e}")
    
    try:
        return AppConfig(
            criteria=CriteriaConfig(**raw.get("criteria", {})),
            cache=CacheConfig(**raw.get("cache", {})),
            processing=ProcessingConfig(**raw.get("processing", {})),
            model=ModelConfig(**raw.get("model", {})),
            batch_files=BatchFilesConfig(**raw.get("batch_files", {})),
            run_defaults=RunDefaultsConfig(**raw.get("run_defaults", {})),
            url_builder=UrlBuilder(**raw.get("url_builder", {})),
        )
    except TypeError as e:
        raise TypeError(f"Invalid config structure: {e}")