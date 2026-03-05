import os
import threading
import time
from typing import Callable, List, Optional
from faster_whisper import WhisperModel
import torch
from datetime import datetime
import librosa
import whisper
from Setting import *
from dataclasses import asdict, dataclass
from data.database import Transcription


@dataclass
class QueueItem:
    id: str
    filename: str
    file_path: str
    language: str
    model_name: str
    add_info: bool = False
    vad_filter: bool = True
    beam_size: int = 5
    temperature: float = 0.0
    best_of: int = 5
    compression_ratio_threshold: float = 2.4
    no_repeat_ngram_size: int = 0
    vad_parameters: Optional[dict] = None
    patience: Optional[float] = None
    status: str = "pending"  # pending, processing, completed, error
    progress: int = 0
    created_at: Optional[str]  = None
    
    def __post_init__(self):
        if self.vad_parameters is None:
            self.vad_parameters = {"min_silence_duration_ms": 1000}
        if self.created_at is None:
            self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
    def to_dict(self):
        return asdict(self)


class Transcriber:
    def __init__(self, callback: Optional[Callable] = None, workers: int = 1, cpu_threads: int = 4):
        
        self.__current_status: str = "idle"
        self.__current_file: str = ""
        self._lock = threading.Lock()
        self._callback: Optional[Callable] = callback
        self._stop_flag: bool = False
        self._current_device: Optional[str] = None
        self.__workers: int = workers
        self.__cpu_threads: int = cpu_threads
        
        torch.set_float32_matmul_precision("high")
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        
    def getCurrentFile(self) -> str:
        return self.__current_file
    
    def getCurrentStatus(self) -> str:
        return self.__current_status
    
    def stop_transcription(self):
        """Imposta il flag per fermare l'esecuzione della trascrizione corrente."""
        #with self._lock:
        self._stop_flag = True
    
    def get_current_device(self) -> Optional[str]:
        """Restituisce il device su cui sta venendo eseguito il modello o None se non è in esecuzione."""
        
        if self.__current_status == "idle":
            return None 
        return self._current_device
       
    def __format_time(self, seconds) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"    
    
    
    def transcribe(self, item: QueueItem, updateFunc: Callable) -> Optional[Transcription]:
        
        # Resetta il flag di stop all'inizio della trascrizione
        with self._lock:
            self._stop_flag = False
            self._current_device = "cuda" if torch.cuda.is_available() else "cpu"
            self.__current_file = item.filename
        
        total_duration = librosa.get_duration(path=item.file_path)
        text_segments: List[str] = []   
        
        logger.info(f"Audio duration: {self.__format_time(total_duration)}") 
        logger.info(f"Current transcription: {item.filename}")

        
        try:     
            item.status = "processing"
            self.__current_status = "processing"
                
            
            #https://developer.nvidia.com/rdp/cudnn-archive
            model = WhisperModel(
                model_size_or_path=item.model_name,
                device=self._current_device,
                device_index=0,
                #compute_type="float16" if torch.cuda.is_available() else "default",
                cpu_threads=self.__cpu_threads,
                num_workers=self.__workers
            )
            
            segments, info = model.transcribe(
                item.file_path,
                language=item.language if item.language and item.language != "auto" else None,
                task="transcribe",
                beam_size=item.beam_size,
                vad_filter=item.vad_filter,
                vad_parameters=item.vad_parameters,
                temperature=[item.temperature],
                # best_of=item.best_of,
                compression_ratio_threshold=item.compression_ratio_threshold,
                no_repeat_ngram_size=item.no_repeat_ngram_size,
                # patience=item.patience if item.patience is not None else 1,
            )
            #print(f"Detected language '{info.language}' with probability {info.language_probability:.2f}")

            last_int_progress_percent = -1
            last_update_time = time.time()
            dt = 0.5  # intervallo minimo tra gli aggiornamenti in secondi
            
            for segment in segments:
                
                # check stop
                if self._stop_flag:
                    with self._lock:
                        logger.info("Transcriber stopped!")
                        self.__current_status = "stopped"
                        break
                 
                # Gestione Progresso
                progress_percent = (segment.end / total_duration) * 100 if total_duration > 0 else 0
                int_progress_percent = min(100, int(progress_percent))
                #logger.info(f"[{item.filename}] Segment {segment.start:.2f}s to {segment.end:.2f}s: {segment.text} (Progress: {progress_percent:.3f}%)")
                
                # scrivi testo
                if item.add_info:
                    segmentrange = f"[{self.__format_time(segment.start)} -> {self.__format_time(segment.end)}]"
                    progress_info = f"[Progress: {progress_percent:.3f}%]"
                    data = f"{segmentrange} {progress_info} "
                    fixed_data = f"{data:<45}"
                    line = f"{fixed_data}: {segment.text}"
                else:
                    line = segment.text
                    
                text_segments.append(line)
                
                if int_progress_percent > last_int_progress_percent and (time.time() - last_update_time >= dt):
                    with self._lock:
                        last_int_progress_percent = int_progress_percent
                        item.progress = int_progress_percent
                        last_update_time = time.time()
                    
                    if updateFunc:
                        updateFunc()
                
            # Costruzione oggetto finale
            final_status = "completed" if not self._stop_flag else "stopped"
            
            return Transcription(
                id=item.id,
                display_name=item.filename,
                original_filename=item.filename,
                language=info.language if info else item.language,
                model=item.model_name,
                temperature=item.temperature,
                created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                status="completed",
                content="\n".join(text_segments) # Uniamo tutto in una stringa
            )

        except Exception as e:
            print(f"Error during transcription: {e}")
            self.__current_status = "error"
            return None
        
        finally:
            with self._lock:
                self.__current_file = ""
                if self.__current_status == "processing":
                    self.__current_status = "idle"
            if updateFunc:
                updateFunc()