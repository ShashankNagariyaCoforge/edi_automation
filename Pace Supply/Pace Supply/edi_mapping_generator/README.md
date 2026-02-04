# EDI Mapping Generator

Automated EDI mapping generation tool that analyzes partner PDF specifications and generates mapping files using AI.

## Features

- **PDF Analysis**: Extracts text from partner EDI specification PDFs
- **AI-Powered Mapping**: Uses OpenAI or Anthropic to generate EDI-to-ERP field mappings
- **Parallel Processing**: Processes multiple record types concurrently for faster execution
- **Excel Output**: Generates properly formatted mapping Excel files
- **Comprehensive Logging**: Detailed logs with automatic cleanup of files older than 10 days

## Prerequisites

- Python 3.8 or higher
- API key for OpenAI or Anthropic

## Installation

1. **Clone/Copy the project folder**

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure API settings**:
   Edit `config.yaml` with your API key:
   ```yaml
   api_provider: "openai"  # or "anthropic"
   api_key: "your-api-key-here"
   model: "gpt-4o"
   api_key: "your-api-key-here"
   model: "gpt-4o"
   max_threads: 5
   ```

## Web Application (New)

The project now includes a modern Web UI and Agentic Copilot.

### 1. Start Backend API
```bash
cd src
python api_server.py
# Server will start at http://0.0.0.0:8001
```

### 2. Start Frontend UI
```bash
cd src/web
npm install
npm run dev -- --host --port 5174
# UI will be available at http://localhost:5174
```

## Folder Structure

```
edi_mapping_generator/
├── main.py                 # Main entry point
├── config.yaml             # API configuration
├── requirements.txt        # Python dependencies
├── README.md               # This file
├── src/                    # Source modules
│   ├── __init__.py
│   ├── ai_client.py        # AI/LLM integration
│   ├── excel_reader.py     # Excel file parsing
│   ├── excel_writer.py     # Output file generation
│   ├── logger.py           # Logging with auto-cleanup
│   ├── parallel_executor.py # Concurrent processing
│   ├── pdf_extractor.py    # PDF text extraction
│   └── record_processor.py # Record-level processing
├── input/                  # Place input files here
│   ├── partner_spec.pdf
│   ├── ERP_definition.xlsx
│   └── inbound_X12_to_oracle.xlsx
├── output/                 # Generated files appear here
└── logs/                   # Log files (auto-cleaned after 10 days)
```

## Input Files

Place these files in the `input/` folder:

| File | Description |
|------|-------------|
| `partner_spec.pdf` | Trading partner's EDI specification PDF |
| `ERP_definition.xlsx` | ERP field definition file with record layouts |
| `inbound_X12_to_oracle.xlsx` | Mapping template (columns B-E, J will be populated) |

## Usage

### Basic Usage
```bash
python main.py
```

### Custom Paths
```bash
python main.py --input ./my_input --output ./my_output --config my_config.yaml
```

### All Options
```bash
python main.py --help
```

| Option | Default | Description |
|--------|---------|-------------|
| `--input`, `-i` | `input` | Input directory |
| `--output`, `-o` | `output` | Output directory |
| `--config`, `-c` | `config.yaml` | Configuration file |
| `--logs`, `-l` | `logs` | Log directory |

## Output

The tool generates:

1. **Mapping Excel File**: `output/generated_mapping_YYYYMMDD_HHMMSS.xlsx`
   - Sheet "Inbound X12 to Oracle" with columns B-E, J populated
   - Sheet "Summary" with processing statistics

2. **Log Files**: `logs/mapping_generator_YYYYMMDD_HHMMSS.log`
   - Detailed processing logs
   - Automatically deleted after 10 days

## Configuration

### config.yaml Options

```yaml
# Your company's LLM API base URL
llm_base_url: "https://your-company-llm-portal.com/v1"

# Model name provided by your company
llm_model: "gpt-4o"

# API Key from your company's portal
llm_api_key: "your-api-key-here"

# Maximum parallel threads for processing records
max_threads: 5

# Request timeout in seconds
timeout: 120

# Retry attempts for failed API calls
max_retries: 3
```

## Building as EXE (Windows)

To create a standalone executable:

1. **Install PyInstaller**:
   ```bash
   pip install pyinstaller
   ```

2. **Build the executable**:
   ```bash
   pyinstaller --onefile --name edi_mapping_generator main.py
   ```

3. **Find the executable** in `dist/edi_mapping_generator.exe`

4. **Distribute** with:
   - `edi_mapping_generator.exe`
   - `config.yaml`
   - `input/` folder (empty, for user to add files)
   - `output/` folder (empty)
   - `logs/` folder (empty)

## Troubleshooting

### "API key not set"
Edit `config.yaml` and replace `your-api-key-here` with your actual API key from your company's LLM portal.

### "File not found"
Ensure all required files are in the `input/` folder with exact names:
- `partner_spec.pdf`
- `ERP_definition.xlsx`
- `inbound_X12_to_oracle.xlsx`

### "JSON parse error"
The AI response wasn't valid JSON. The tool will retry automatically. If persistent, try a different model.

### Slow processing
Reduce `max_threads` in config if you're hitting API rate limits.

## License

Internal use only.
