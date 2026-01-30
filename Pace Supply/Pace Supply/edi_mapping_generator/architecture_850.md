
# EDI 850 (Inbound Purchase Order) Architecture

## Overview
The 850 flow architecture follows a modern Client-Server pattern, leveraging a React frontend for user interaction and a Python FastAPI backend for core processing, integrated with an external LLM for intelligent extraction and mapping.

## System Components

### 1. Client Layer (Frontend)
*   **React Application**: Single Page Application (SPA) built with Vite/React.
*   **Role**: Handles file uploads (PDF + EDI), displays processing status, renders the editable Mapping Grid, and manages file downloads.

### 2. Server Layer (Backend)
*   **API Gateway**: `api_server.py` (FastAPI). Exposes REST endpoints for upload, generation, and updates.
*   **Service Layer**: `MappingService`. Orchestrates the session state and calls specific processors.
*   **Core Logic**: 
    *   `PDFConstraintExtractor`: Parses PDF for mandatory fields.
    *   `RecordProcessor`: Handles record-by-record mapping logic (Phase 3).
    *   `ExcelGenerator`: Formats the final output.

### 3. Intelligence Layer (AI)
*   **AI Client**: `src/ai_client.py`. Manages authentication and communication with the External LLM.
*   **External LLM**: Processes complex prompts to extract constraints and perform semantic mapping.

## Architecture Diagram

```mermaid
graph TD
    subgraph Client ["Client Layer (Frontend)"]
        UI[React SPA]
        Upload[File Upload Component]
        Grid[Mapping Grid Editor]
    end

    subgraph Server ["Server Layer (Backend)"]
        API[FastAPI Server]
        
        subgraph Internal ["Internal Components"]
            Service[MappingService]
            PDF_Ext[PDFConstraintExtractor]
            Rec_Proc[RecordProcessor]
            Gen[ExcelGenerator]
        end
        
        AI_Client[AIClient Adapter]
    end

    subgraph External ["External Services"]
        LLM[Large Language Model API]
    end

    %% Data Flow
    Upload -- "POST /api/upload (PDF + EDI)" --> API
    API -- "Files" --> Service
    Service -- "Extract Constraints" --> PDF_Ext
    
    PDF_Ext -- "Prompt" --> AI_Client
    Rec_Proc -- "Prompt (Per Record)" --> AI_Client
    
    AI_Client -- "JSON Response" --> PDF_Ext
    AI_Client -- "JSON Response" --> Rec_Proc
    
    Service -- "1. Bootstrap & Extract" --> PDF_Ext
    Service -- "2. Map Records" --> Rec_Proc
    Service -- "3. Build Excel" --> Gen
    
    AI_Client <--> LLM
    
    Gen -- "Generated .xlsx" --> Service
    Service -- "Mapping Data" --> API
    API -- "JSON Grid Data" --> Grid
    
    style Client fill:#e3f2fd,stroke:#1565c0
    style Server fill:#f3e5f5,stroke:#4a148c
    style Internal fill:#ffffff,stroke:#7b1fa2,stroke-dasharray: 5 5
    style External fill:#fff3e0,stroke:#e65100
    style LLM fill:#ffcc80,stroke:#f57c00
```
