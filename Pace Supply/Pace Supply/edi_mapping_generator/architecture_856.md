
# EDI 856 (Outbound Advance Ship Notice) Architecture

## Overview
The 856 flow follows a specialized pipeline designed for Outbound mapping. It shares the same Frontend and API shell as the 850 flow but utilizes a distinct set of internal processing components optimized for extracting Vendor requirements and mapping them to ERP output fields.

## System Components

### 1. Client Layer (Frontend)
*   **React Application**: Provides the "856 Workflow" UI.
*   **Role**: Handles PDF-only upload, renders the 856-specific Grid (columns A-H structure), allows cell editing, and manages Excel download.

### 2. Server Layer (Backend)
*   **API Gateway**: `api_server.py`. Routes requests to the 856-specific endpoints (`/api/856/*`).
*   **Service Layer**: `MappingService`. Acts as the controller, initializing the 856 processors and managing session data.
*   **Core Logic**:
    *   `PdfProcessor856`: Specialized extractor for "Mandatory" and "Must Use" segments from Vendor PDFs.
    *   `MappingEngine856`: AI-driven engine that aligns Vendor fields to ERP Interface fields and determines Logic Types (Constant, Translation, etc.).
    *   `ExcelBuilder856`: Generates the specific `PaceSupply_856_Outbound.xlsx` format.

### 3. Intelligence Layer (AI)
*   **AI Client**: Shared adapter for LLM communication.
*   **External LLM**: Performs two key tasks: 1) Structure extraction from PDF text, 2) Semantic mapping of Field Definitions.

## Architecture Diagram

```mermaid
graph TD
    subgraph Client ["Client Layer (Frontend)"]
        UI[React SPA]
        Upload[PDF Upload]
        Grid[856 Grid Editor]
    end

    subgraph Server ["Server Layer (Backend)"]
        API[FastAPI Server]
        
        subgraph Internal ["Internal Components (856)"]
            Service[MappingService]
            PDF_Proc[PdfProcessor856]
            Map_Eng[MappingEngine856]
            XLS_Bld[ExcelBuilder856]
        end
        
        AI_Client[AIClient Adapter]
    end

    subgraph External ["External Services"]
        LLM[Large Language Model API]
    end

    %% Data Flow
    Upload -- "POST /api/856/upload (PDF)" --> API
    API -- "PDF File" --> Service
    
    Service -- "1. Extract Mandatory Segments" --> PDF_Proc
    PDF_Proc -- "Extraction Prompt" --> AI_Client
    
    Service -- "2. Generate Mappings" --> Map_Eng
    Map_Eng -- "Semantic Mapping Prompt" --> AI_Client
    
    AI_Client <--> LLM
    
    Map_Eng -- "Mapped Data (JSON)" --> Service
    Service -- "3. Build Excel" --> XLS_Bld
    
    XLS_Bld -- "Formatted .xlsx" --> Service
    Service -- "Grid Data" --> API
    API -- "Render Grid" --> Grid
    
    style Client fill:#e3f2fd,stroke:#1565c0
    style Server fill:#f3e5f5,stroke:#4a148c
    style Internal fill:#ffffff,stroke:#7b1fa2,stroke-dasharray: 5 5
    style External fill:#fff3e0,stroke:#e65100
    style LLM fill:#ffcc80,stroke:#f57c00
```
