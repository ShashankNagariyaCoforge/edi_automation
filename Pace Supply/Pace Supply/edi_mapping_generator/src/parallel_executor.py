"""
Parallel executor module for concurrent record processing.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any, Callable
from .logger import get_logger


class ParallelExecutor:
    """Manages parallel execution of record processing tasks."""
    
    def __init__(self, max_threads: int = 5):
        """
        Initialize parallel executor.
        
        Args:
            max_threads: Maximum number of concurrent threads
        """
        self.max_threads = max_threads
        self.logger = get_logger()
    
    def process_records_parallel(
        self,
        records: Dict[str, List[Dict[str, Any]]],
        processor_func: Callable[[str, List[Dict[str, Any]]], Dict[str, Dict[str, Any]]]
    ) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """
        Process multiple records in parallel.
        
        Args:
            records: Dictionary of record_num -> list of field definitions
            processor_func: Function to process each record (takes record_num, fields)
        
        Returns:
            Dictionary of record_num -> field mappings
        """
        results = {}
        total_records = len(records)
        
        self.logger.info(f"Starting parallel processing of {total_records} records with {self.max_threads} threads")
        
        with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            # Submit all tasks
            future_to_record = {
                executor.submit(processor_func, record_num, fields): record_num
                for record_num, fields in records.items()
            }
            
            # Collect results as they complete
            completed = 0
            for future in as_completed(future_to_record):
                record_num = future_to_record[future]
                completed += 1
                
                try:
                    result = future.result()
                    results[record_num] = result
                    self.logger.info(f"Completed record {record_num} ({completed}/{total_records})")
                except Exception as e:
                    self.logger.error(f"Record {record_num} failed: {e}")
                    results[record_num] = {}
        
        self.logger.info(f"Parallel processing complete: {len(results)}/{total_records} records processed")
        
        return results
