"""Patent data source adapters."""

from engine.adapters.base import PatentAdapter
from engine.adapters.google_patents import GooglePatentsExportAdapter
from engine.adapters.importer import PatentDatasetImporter
from engine.adapters.uspto import USPTOFileWrapperJsonAdapter, USPTOGrantXmlAdapter
from engine.adapters.wos_adapter import WoSAdapter

__all__ = [
    "PatentAdapter", "PatentDatasetImporter", "GooglePatentsExportAdapter",
    "USPTOGrantXmlAdapter", "USPTOFileWrapperJsonAdapter", "WoSAdapter",
]
