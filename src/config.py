import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Any, Dict


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
    """Loads the config file and converts all relative paths to absolute paths."""
    
    path = Path(path).resolve() 
    base_dir = path.parent 
    
    try:
        with open(path, encoding="utf-8") as f:
            raw: Dict[str, Any] = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file not found: {path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in config file: {e}")

    
    def _resolve_path(parent_key: str, child_key: str):
        if parent_key in raw and child_key in raw[parent_key]:
            raw_path = raw[parent_key][child_key]
            absolute_path = (base_dir / raw_path).resolve()            
            raw[parent_key][child_key] = str(absolute_path)
            
    _resolve_path("cache", "directory")
    _resolve_path("batch_files", "directory")
    _resolve_path("run_defaults", "file_path")
    _resolve_path("run_defaults", "output_path")
    
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
        required_keys = ['criteria', 'cache', 'processing', 'model', 'batch_files', 'run_defaults', 'url_builder']
        missing_keys = [k for k in required_keys if k not in raw]
        if missing_keys:
             raise TypeError(f"Invalid config structure: Missing top-level keys: {', '.join(missing_keys)}")
        else:
             raise TypeError(f"Invalid config structure: {e}")