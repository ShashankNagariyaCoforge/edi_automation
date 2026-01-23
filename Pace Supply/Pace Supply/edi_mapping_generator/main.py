#!/usr/bin/env python3
"""
EDI Mapping Generator - Main Entry Point

Automates the generation of EDI mapping files by analyzing sample EDI files
and generating mappings for ERP field definitions using AI.
"""
import argparse
import sys
import time
import yaml
from pathlib import Path
from typing import Dict, Any

from src.logger import setup_logger, get_logger
from src.edi_parser import parse_edi_file, create_edi_summary
from src.excel_reader import read_erp_structure
from src.excel_writer import write_mapping_output, create_summary_sheet
from src.ai_client import AIClient
from src.record_processor import RecordProcessor
from src.parallel_executor import ParallelExecutor
from src.pdf_constraint_extractor import PdfConstraintExtractor



def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """Load configuration from YAML file."""
    config_file = Path(config_path)
    
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    
    # Validate required fields
    required = ["llm_base_url", "llm_api_key", "llm_model"]
    for field in required:
        if field not in config or not config[field]:
            raise ValueError(f"Missing required config field: {field}")
    
    if config["llm_api_key"] == "your-api-key-here":
        raise ValueError("Please set your API key in config.yaml")
    
    return config


def validate_input_files(input_dir: str, edi_filename: str = None) -> Dict[str, str]:
    """Validate that all required input files exist."""
    input_path = Path(input_dir)
    
    # Look for any .txt file if edi_filename not specified
    if not edi_filename:
        txt_files = list(input_path.glob("*.txt"))
        if txt_files:
            edi_filename = txt_files[0].name
        else:
            edi_filename = "sample_850.txt" # Default fallback

    # Look for any .pdf file
    pdf_filename = "partner_spec.pdf"
    pdf_files = list(input_path.glob("*.pdf"))
    if pdf_files:
        pdf_filename = pdf_files[0].name
    
    required_files = {
        edi_filename: "Sample EDI file",
        pdf_filename: "Vendor PDF Spec",
        "ERP_definition.xlsx": "ERP definition file",
        "inbound_X12_to_oracle.xlsx": "Mapping template file"
    }
    
    file_paths = {}
    missing = []
    
    for filename, description in required_files.items():
        file_path = input_path / filename
        if not file_path.exists():
            missing.append(f"  - {filename} ({description})")
        
        key = "pdf_spec" if filename.endswith(".pdf") else \
              "edi_sample" if filename.endswith(".txt") else filename
        file_paths[key] = str(file_path)
    
    if missing:
        raise FileNotFoundError(
            f"Missing required input files in '{input_dir}':\n" + "\n".join(missing)
        )
    
    return file_paths


def main():
    """Main entry point for the EDI Mapping Generator."""
    parser = argparse.ArgumentParser(
        description="Generate EDI mappings from sample EDI files using AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example usage:
  python main.py
  python main.py --input ./my_input --output ./my_output
  python main.py --edi-file sample_850.txt
        """
    )
    
    parser.add_argument(
        "--input", "-i",
        default="input",
        help="Input directory containing EDI sample and Excel files (default: input)"
    )
    
    parser.add_argument(
        "--output", "-o",
        default="output",
        help="Output directory for generated files (default: output)"
    )
    
    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="Configuration file path (default: config.yaml)"
    )
    
    parser.add_argument(
        "--logs", "-l",
        default="logs",
        help="Log directory (default: logs)"
    )
    
    parser.add_argument(
        "--edi-file", "-e",
        help="Specific EDI sample filename (default: automatically finds first .txt in input dir)"
    )
    
    args = parser.parse_args()
    
    # Initialize logger
    logger = setup_logger(log_dir=args.logs)
    logger.info("=" * 60)
    logger.info("EDI Mapping Generator Started")
    logger.info("=" * 60)
    
    start_time = time.time()
    
    try:
        # Load configuration
        logger.info("Loading configuration...")
        config = load_config(args.config)
        logger.info(f"Using LLM: {config['llm_base_url']}, model: {config['llm_model']}")
        
        # Validate input files
        logger.info("Validating input files...")
        input_files = validate_input_files(args.input, args.edi_file)
        logger.info(f"Input files: {input_files}")
        
        # Initialize AI client
        logger.info("Initializing AI client...")
        ai_client = AIClient(
            base_url=config["llm_base_url"],
            api_key=config["llm_api_key"],
            model=config["llm_model"],
            timeout=config.get("timeout", 120),
            max_retries=config.get("max_retries", 3),
            auth_type=config.get("auth_type", "bearer"),
            auth_header_name=config.get("auth_header_name")
        )

        # 1. Parse EDI Sample
        logger.info("Reading and parsing EDI sample file...")
        with open(input_files["edi_sample"], 'r') as f:
            edi_text = f.read()
            
        edi_parsed = parse_edi_file(edi_text)
        logger.info(f"Parsed {len(edi_parsed)} unique segment types from sample")

        # 2. Extract Constraints from PDF
        logger.info("Extracting constraints from PDF (Phase 2)...")
        extractor = PdfConstraintExtractor(ai_client)
        constraints = extractor.extract_constraints(input_files["pdf_spec"])
        
        # 3. Read Excel Structure (Phase 1)
        # User requested to use the inbound template as the source and target
        logger.info("Reading output template structure (Phase 1)...")
        structure = read_erp_structure(input_files["inbound_X12_to_oracle.xlsx"])
        
        # Initialize record processor (Phase 3)
        processor = RecordProcessor(ai_client, edi_parsed, constraints)
        
        # Initialize parallel executor
        executor = ParallelExecutor(max_threads=config.get("max_threads", 5))
        
        # Process all records in parallel
        logger.info("Processing records (Phase 3)...")
        all_mappings = executor.process_records_parallel(
            records=structure,
            processor_func=processor.process_record
        )
        
        # Write output (Phase 4)
        logger.info("Writing output file (Phase 4)...")
        output_file = write_mapping_output(
            structure=structure,
            mappings=all_mappings,
            output_path=args.output
        )
        
        # Calculate statistics
        processing_time = time.time() - start_time
        total_fields = sum(len(m) for m in all_mappings.values())
        
        stats = {
            "total_records": len(all_mappings),
            "total_fields": total_fields,
            "processing_time": processing_time
        }
        
        # Add summary sheet
        create_summary_sheet(output_file, all_mappings, stats)
        
        # Print summary
        logger.info("=" * 60)
        logger.info("PROCESSING COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Records processed: {stats['total_records']}")
        logger.info(f"Fields mapped: {stats['total_fields']}")
        logger.info(f"Processing time: {processing_time:.2f} seconds")
        logger.info(f"Output file: {output_file}")
        logger.info("=" * 60)
        
        return 0
    
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return 1
    
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return 1
    
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
