from abc import ABC, abstractmethod
import json
import os
from pathlib import Path
import uuid
from typing import List, Dict, Any, Optional


class DataManager(ABC):
    """Abstract base class for data management"""
    
    @abstractmethod
    def get_all_links(self) -> List[Dict[str, Any]]:
        """Get all links"""
        pass
    
    @abstractmethod
    def create_link(self, link_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new link"""
        pass
    
    @abstractmethod
    def update_link(self, link_id: str, link_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update an existing link"""
        pass
    
    @abstractmethod
    def delete_link(self, link_id: str) -> bool:
        """Delete a link"""
        pass
    
    @abstractmethod
    def reorder_links(self, links: List[Dict[str, Any]]) -> None:
        """Reorder links"""
        pass
    
    @abstractmethod
    def export_data(self) -> Dict[str, Any]:
        """Export all data"""
        pass
    
    @abstractmethod
    def import_data(self, data: Dict[str, Any]) -> None:
        """Import data"""
        pass
    
    @abstractmethod
    def get_settings(self) -> Dict[str, Any]:
        """Get application settings"""
        pass
    
    @abstractmethod
    def update_settings(self, settings_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update application settings"""
        pass


class JSONDataManager(DataManager):
    """JSON file-based data manager"""
    
    def __init__(self, file_path: str = 'data.json'):
        self.file_path = Path(__file__).parent / file_path
        self._ensure_file_exists()
    
    def _ensure_file_exists(self):
        """Ensure the data file exists with default structure"""
        if not self.file_path.exists():
            default_data = {
                'links': [],
                'settings': {
                    'theme': 'light',
                    'buttonSize': 150
                }
            }
            self._write_data(default_data)
    
    def _read_data(self) -> Dict[str, Any]:
        """Read data from JSON file"""
        with open(self.file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _write_data(self, data: Dict[str, Any]) -> None:
        """Write data to JSON file"""
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def get_all_links(self) -> List[Dict[str, Any]]:
        data = self._read_data()
        return data.get('links', [])
    
    def create_link(self, link_data: Dict[str, Any]) -> Dict[str, Any]:
        data = self._read_data()
        link_data['id'] = str(uuid.uuid4())
        data['links'].append(link_data)
        self._write_data(data)
        return link_data
    
    def update_link(self, link_id: str, link_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        data = self._read_data()
        for i, link in enumerate(data['links']):
            if link['id'] == link_id:
                link_data['id'] = link_id
                data['links'][i] = link_data
                self._write_data(data)
                return link_data
        return None
    
    def delete_link(self, link_id: str) -> bool:
        data = self._read_data()
        original_length = len(data['links'])
        data['links'] = [link for link in data['links'] if link['id'] != link_id]
        if len(data['links']) < original_length:
            self._write_data(data)
            return True
        return False
    
    def reorder_links(self, links: List[Dict[str, Any]]) -> None:
        data = self._read_data()
        data['links'] = links
        self._write_data(data)
    
    def export_data(self) -> Dict[str, Any]:
        return self._read_data()
    
    def import_data(self, data: Dict[str, Any]) -> None:
        self._write_data(data)
    
    def get_settings(self) -> Dict[str, Any]:
        data = self._read_data()
        return data.get('settings', {'theme': 'light', 'buttonSize': 150})
    
    def update_settings(self, settings_data: Dict[str, Any]) -> Dict[str, Any]:
        data = self._read_data()
        data['settings'] = {**data.get('settings', {}), **settings_data}
        self._write_data(data)
        return data['settings']


class PostgreSQLDataManager(DataManager):
    """PostgreSQL database data manager (placeholder implementation)"""
    
    def __init__(self):
        # TODO: Initialize PostgreSQL connection
        raise NotImplementedError("PostgreSQL implementation not yet available")
    
    def get_all_links(self) -> List[Dict[str, Any]]:
        raise NotImplementedError()
    
    def create_link(self, link_data: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError()
    
    def update_link(self, link_id: str, link_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        raise NotImplementedError()
    
    def delete_link(self, link_id: str) -> bool:
        raise NotImplementedError()
    
    def reorder_links(self, links: List[Dict[str, Any]]) -> None:
        raise NotImplementedError()
    
    def export_data(self) -> Dict[str, Any]:
        raise NotImplementedError()
    
    def import_data(self, data: Dict[str, Any]) -> None:
        raise NotImplementedError()
    
    def get_settings(self) -> Dict[str, Any]:
        raise NotImplementedError()
    
    def update_settings(self, settings_data: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError()


class MongoDBDataManager(DataManager):
    """MongoDB data manager (placeholder implementation)"""
    
    def __init__(self):
        # TODO: Initialize MongoDB connection
        raise NotImplementedError("MongoDB implementation not yet available")
    
    def get_all_links(self) -> List[Dict[str, Any]]:
        raise NotImplementedError()
    
    def create_link(self, link_data: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError()
    
    def update_link(self, link_id: str, link_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        raise NotImplementedError()
    
    def delete_link(self, link_id: str) -> bool:
        raise NotImplementedError()
    
    def reorder_links(self, links: List[Dict[str, Any]]) -> None:
        raise NotImplementedError()
    
    def export_data(self) -> Dict[str, Any]:
        raise NotImplementedError()
    
    def import_data(self, data: Dict[str, Any]) -> None:
        raise NotImplementedError()
    
    def get_settings(self) -> Dict[str, Any]:
        raise NotImplementedError()
    
    def update_settings(self, settings_data: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError()


class DataManagerFactory:
    """Factory class for creating data managers"""
    
    @staticmethod
    def create(storage_type: str) -> DataManager:
        """Create a data manager based on storage type"""
        storage_type = storage_type.upper()
        
        if storage_type == 'JSON':
            return JSONDataManager()
        elif storage_type == 'POSTGRES':
            return PostgreSQLDataManager()
        elif storage_type == 'MONGODB':
            return MongoDBDataManager()
        else:
            raise ValueError(f"Unknown storage type: {storage_type}")
