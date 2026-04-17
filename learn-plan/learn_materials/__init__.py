"""Materials ownership primitives for the learn-plan skill cluster."""

from .downloader import (
    download_file,
    generate_local_path,
    guess_extension,
    is_downloadable_url,
    process_materials,
    should_download,
    update_material_cache_status,
)
from .index_schema import (
    CACHE_FIELDS,
    INDEX_SCHEMA_VERSION,
    PLANNING_FIELDS,
    get_index_entries,
    normalize_materials_index,
)
from .merge import merge_material_entries, merge_reading_segments
from .planner import build_default_material_entries, build_materials_index, enrich_material_entry
from .preprocessing import default_preprocessing_state, preprocess_material, update_preprocessing_status
from .segment_cache import get_segment_excerpt, load_segment_cache, segment_cache_path, write_segment_cache
from .segments import (
    build_reading_segments,
    build_special_reading_segments,
    group_topics_for_segments,
    infer_material_recommended_day,
)

__all__ = [
    "CACHE_FIELDS",
    "INDEX_SCHEMA_VERSION",
    "PLANNING_FIELDS",
    "build_default_material_entries",
    "build_materials_index",
    "build_reading_segments",
    "build_special_reading_segments",
    "default_preprocessing_state",
    "download_file",
    "enrich_material_entry",
    "generate_local_path",
    "get_index_entries",
    "get_segment_excerpt",
    "group_topics_for_segments",
    "guess_extension",
    "infer_material_recommended_day",
    "is_downloadable_url",
    "load_segment_cache",
    "merge_material_entries",
    "merge_reading_segments",
    "normalize_materials_index",
    "preprocess_material",
    "process_materials",
    "segment_cache_path",
    "should_download",
    "update_material_cache_status",
    "update_preprocessing_status",
    "write_segment_cache",
]
