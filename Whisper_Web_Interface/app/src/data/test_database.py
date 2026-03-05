import unittest
import threading
import os
import time
from datetime import datetime
# Assicurati che il nome del file importato corrisponda al tuo file (es. database_manager.py)
from database import DatabaseManager, Transcription 

class TestDatabaseIntegrity(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        print("\n" + "="*50)
        print(" INIZIO TEST DI INTEGRITÀ DATABASE ")
        print("="*50)

    def setUp(self):
        self.test_db = f"test_db_{int(time.time())}.db"
        print(f"\n[SETUP] Creato DB temporaneo: {self.test_db}")
        self.db_manager = DatabaseManager(self.test_db)

    def tearDown(self):
        # Chiudiamo la connessione prima di eliminare il file
        self.db_manager._conn.close()
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
            print(f"[TEARDOWN] Database rimosso: {self.test_db}")

    def test_1_model_and_mapping(self):
        print("--- Test 1: Verifica Modello e Mapping ---")
        data = Transcription(
            id="test_01",
            display_name=None, # Verifichiamo il fallback su original_filename
            original_filename="audio_lezione.mp3",
            language="it",
            model="whisper-large",
            temperature=0.0,
            created_at=datetime.now().isoformat(),
            status="completed",
            content="Contenuto di prova"
        )
        
        print(f" -> Salvataggio oggetto: {data.id}")
        self.db_manager.add_transcription(data)
        
        print(" -> Recupero oggetto e verifica mapping...")
        retrieved = self.db_manager.get_transcription("test_01")
        self.assertIsNotNone(retrieved)
        
        assert retrieved is not None
        self.assertEqual(retrieved.display_name, "audio_lezione.mp3") # Test fallback
        print(f" OK: Mapping corretto. Display name recuperato: {retrieved.display_name}")

    def test_2_size_limit(self):
        print("--- Test 2: Verifica Limite Dimensione (2MB) ---")
        # Generiamo circa 2.1 MB di testo
        heavy_content = "A" * (2 * 1024 * 1024 + 100)
        data = Transcription(
            id="oversize",
            display_name="Large File",
            original_filename="large.wav",
            language="en",
            model="base",
            temperature=0.0,
            created_at="now",
            status="error",
            content=heavy_content
        )
        
        print(" -> Tentativo di inserimento dati > 2MB...")
        result = self.db_manager.add_transcription(data)
        self.assertFalse(result)
        print(" OK: Il sistema ha correttamente rifiutato il file troppo grande.")

    def test_3_thread_safety_concurrency(self):
        print("--- Test 3: Stress Test Thread-Safety (10 Thread) ---")
        num_threads = 10
        barrier = threading.Barrier(num_threads) # Per farli partire tutti insieme

        def worker(thread_idx):
            # Aspetta gli altri per massimizzare la concorrenza
            barrier.wait() 
            t = Transcription(
                id=f"id_thread_{thread_idx}",
                display_name=f"Trascrizione {thread_idx}",
                original_filename="multi.mp3",
                language="it",
                model="small",
                temperature=0.2,
                created_at="now",
                status="completed",
                content=f"Testo generato dal thread {thread_idx}"
            )
            res = self.db_manager.add_transcription(t)
            if res:
                print(f"   [Thread-{thread_idx}] Scrittura completata.")

        threads = []
        for i in range(num_threads):
            th = threading.Thread(target=worker, args=(i,))
            threads.append(th)
            th.start()

        for th in threads:
            th.join()

        print(" -> Verifica integrità dati post-concorrenza...")
        all_data = self.db_manager.get_transcriptions_paginated(1, 20, "created_at", "asc")
        count = len(all_data['items'])
        self.assertEqual(count, num_threads)
        print(f" OK: Tutti i {count} thread hanno scritto correttamente senza deadlock.")

if __name__ == "__main__":
    unittest.main()