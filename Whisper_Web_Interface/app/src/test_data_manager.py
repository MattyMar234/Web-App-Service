# test_data_manager.py

import unittest
import os
import tempfile
import time
import shutil
from datetime import datetime, timedelta

from data_manager import DataManager, GarbageCollector, FileStatus

class TestDataManager(unittest.TestCase):
    
    def __del__(self):
        self.tearDown()

    def setUp(self):
        """Crea un ambiente di test isolato prima di ogni test."""
        # Crea una directory temporanea per i file di test
        self.test_dir = tempfile.TemporaryDirectory()
        self.test_db_path = os.path.join(self.test_dir.name, "test_files.db")
        self.test_files_dir = os.path.join(self.test_dir.name, "files")
        os.makedirs(self.test_files_dir)

        # Inizializza DataManager e GarbageCollector con i percorsi di test
        self.dm = DataManager(self.test_db_path, self.test_files_dir)
        self.gc = GarbageCollector(self.dm, max_file_age_days=1)

    @staticmethod
    def _start_test_section(text) -> None:
        print("-"*40 + f"[{text}]" + "-"*40)

    @staticmethod
    def printTest(func):
        def wrapper(self, *args, **wargs):
            print()
            TestDataManager._start_test_section(func.__name__.upper())
            func(self, *args, **wargs)
        return wrapper

    def tearDown(self):
        """Pulisce l'ambiente di test dopo ogni test."""
        self.test_dir.cleanup()

    @printTest
    def test_initialization(self):
        """Verifica che il database e la directory vengano creati correttamente."""
        self.assertTrue(os.path.exists(self.test_db_path))
        self.assertTrue(os.path.exists(self.test_files_dir))

    @printTest
    def test_insert_and_get_file(self):
        """Inserisce un file e verifica che i dati recuperati siano corretti."""
        config = {"user": "test_user", "priority": 5}
        file_id = self.dm.insert_file("test_file.txt", FileStatus.PENDING, config)
        self.assertIsNotNone(file_id)

        file_data = self.dm.get_file(file_id)
        self.assertIsNotNone(file_data)
        self.assertEqual(file_data['filename'], "test_file.txt")
        self.assertEqual(file_data['status'], FileStatus.PENDING.value)
        self.assertEqual(file_data['config'], config)

    @printTest
    def test_update_status(self):
        """Verifica l'aggiornamento dello stato di un file."""
        
        file_id = self.dm.insert_file("update_status.txt", FileStatus.PENDING)
        self.dm.update_file_status(file_id, FileStatus.COMPLETED)
        
        updated_file = self.dm.get_file(file_id)
        self.assertEqual(updated_file['status'], FileStatus.COMPLETED.value)

    @printTest
    def test_delete_file(self):
        """Verifica la cancellazione di un file e del suo record."""
        # Crea un file fisico
        filename = "delete_me.txt"
        file_path = os.path.join(self.test_files_dir, filename)
        with open(file_path, 'w') as f:
            f.write("test content")
        
        file_id = self.dm.insert_file(filename, FileStatus.COMPLETED)
        self.assertTrue(os.path.exists(file_path))

        # Elimina sia dal DB che dal filesystem
        success = self.dm.delete_file(file_id, delete_physical_file=True)
        self.assertTrue(success)
        self.assertIsNone(self.dm.get_file(file_id))
        self.assertFalse(os.path.exists(file_path))

    @printTest
    def test_count_files(self):
        """Verifica il conteggio dei file."""
        self.assertEqual(self.dm.count_files(), 0)
        self.dm.insert_file("file1.txt", FileStatus.PENDING)
        self.dm.insert_file("file2.txt", FileStatus.PROCESSING)
        self.dm.insert_file("file3.txt", FileStatus.PENDING)
        
        self.assertEqual(self.dm.count_files(), 3)
        self.assertEqual(self.dm.count_files(FileStatus.PENDING), 2)
        self.assertEqual(self.dm.count_files(FileStatus.PROCESSING), 1)
        self.assertEqual(self.dm.count_files(FileStatus.COMPLETED), 0)

    @printTest
    def test_get_oldest_file(self):
        """Verifica il recupero del file più vecchio."""
        # Inserisce file con un piccolo ritardo per garantire timestamp diversi
        id1 = self.dm.insert_file("oldest.txt", FileStatus.PENDING)
        time.sleep(0.01)
        id2 = self.dm.insert_file("newest.txt", FileStatus.PENDING)
        
        oldest = self.dm.get_oldest_file()
        self.assertIsNotNone(oldest)
        self.assertEqual(oldest['id'], id1)

    @printTest
    def test_concurrent_inserts(self):
        """Verifica che inserimenti concorrenti non causino errori o perdita di dati."""
        import threading
        
        num_threads = 5
        inserts_per_thread = 10
        threads = []
        
        def worker(thread_id):
            for i in range(inserts_per_thread):
                try:
                    self.dm.insert_file(f"thread_{thread_id}_file_{i}.txt", FileStatus.PENDING)
                except Exception as e:
                    self.fail(f"Insert failed in thread {thread_id}: {e}")

        # Avvia i thread
        for i in range(num_threads):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Attendi che tutti i thread finiscano
        for thread in threads:
            thread.join()
        
        # Verifica il conteggio finale
        expected_count = num_threads * inserts_per_thread
        final_count = self.dm.count_files()
        self.assertEqual(final_count, expected_count, "Il conteggio finale non corrisponde al valore atteso dopo inserimenti concorrenti.")

    @printTest
    def test_garbage_collector_cleanup_old_files(self):
        """Verifica la rimozione dei file vecchi da parte del GarbageCollector."""
        # Crea un file e un suo record
        filename = "old_file.txt"
        file_path = os.path.join(self.test_files_dir, filename)
        with open(file_path, 'w') as f:
            f.write("old")
        
        file_id = self.dm.insert_file(filename, FileStatus.COMPLETED)
        
        # Modifica manualmente la data di creazione nel DB per renderlo "vecchio"
        old_date = datetime.now() - timedelta(days=2)
        with self.dm._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE files SET created_at = ? WHERE id = ?", (old_date, file_id))
            conn.commit()
        
        # Esegui la pulizia
        removed_count = self.gc.cleanup_old_files()
        
        self.assertEqual(removed_count, 1)
        self.assertIsNone(self.dm.get_file(file_id))
        self.assertFalse(os.path.exists(file_path))

    @printTest
    def test_garbage_collector_cleanup_orphaned_files(self):
        """Verifica la rimozione dei file orfani."""
        # Crea un file fisico senza una entry nel DB
        orphan_filename = "orphan.txt"
        orphan_path = os.path.join(self.test_files_dir, orphan_filename)
        with open(orphan_path, 'w') as f:
            f.write("orphan")
        
        self.assertTrue(os.path.exists(orphan_path))
        
        # Esegui la pulizia
        removed_count = self.gc.cleanup_orphaned_files()
        
        self.assertEqual(removed_count, 1)
        self.assertFalse(os.path.exists(orphan_path))

    @printTest
    def test_garbage_collector_cleanup_missing_files(self):
        """Verifica la rimozione delle entry di file mancanti."""
        # Inserisci un record nel DB senza creare il file fisico
        filename = "missing_file.txt"
        file_id = self.dm.insert_file(filename, FileStatus.COMPLETED)
        
        file_path = os.path.join(self.test_files_dir, filename)
        self.assertFalse(os.path.exists(file_path)) # Assicurati che non esista
        self.assertIsNotNone(self.dm.get_file(file_id)) # Assicurati che il record esista
        
        # Esegui la pulizia
        removed_count = self.gc.cleanup_missing_files()
        
        self.assertEqual(removed_count, 1)
        self.assertIsNone(self.dm.get_file(file_id))


if __name__ == '__main__':
    unittest.main()