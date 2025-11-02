# 🗄️ Developer Archives - Backend

> AI-Powered Semantic Search Engine for GitHub Repositories

Developer Archives is a sophisticated backend system that enables semantic search across GitHub repositories using AI embeddings and vector similarity. The system automatically discovers, processes, and indexes repositories, making them searchable through natural language queries.

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Features](#features)
- [Project Structure](#project-structure)
- [Setup & Installation](#setup--installation)
- [Environment Variables](#environment-variables)
- [Database Schema](#database-schema)
- [API Endpoints](#api-endpoints)
- [AWS Deployment](#aws-deployment)
- [Development](#development)
- [Scripts](#scripts)

---

## 🎯 Overview

Developer Archives consists of three main components:

1. **Discoverer (Lambda)**: Continuously discovers new repositories from GitHub and queues them for processing
2. **Processor (Lambda)**: Processes repositories by extracting README content, generating embeddings, and storing metadata
3. **API (Lambda/API Gateway)**: Provides REST API for semantic search and repository details

### How It Works

```
GitHub API → Discoverer → SQS Queue → Processor → PostgreSQL (pgvector) → API → Frontend
                ↓                          ↓
            DynamoDB              S3 (README Storage)
         (State Tracking)        (Embedding Generation)
```

1. **Discovery Phase**: Discoverer Lambda fetches repositories from GitHub API, tracks state in DynamoDB and sends saved project ids to SQS
2. **Processing Phase**: Processor Lambda reads from SQS, extracts README, generates embeddings using Sentence Transformers
3. **Storage Phase**: Stores embeddings in PostgreSQL with pgvector extension, README content in S3
4. **Search Phase**: API uses vector similarity search to find relevant repositories based on semantic meaning

---

## 🏗️ Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        AWS Cloud                             │
│                                                              │
│  ┌──────────────┐      ┌──────────────┐                    │
│  │  Discoverer  │─────▶│     SQS      │                    │
│  │   Lambda     │      │    Queue     │                    │
│  └──────┬───────┘      └──────┬───────┘                    │
│         │                     │                             │
│         ▼                     ▼                             │
│  ┌──────────────┐      ┌──────────────┐                    │
│  │   DynamoDB   │      │  Processor   │                    │
│  │ (State Store)│      │   Lambda     │                    │
│  └──────────────┘      └──────┬───────┘                    │
│                               │                             │
│                               ▼                             │
│                        ┌──────────────┐                    │
│                        │ PostgreSQL   │                    │
│                        │  (pgvector)  │                    │
│                        └──────┬───────┘                    │
│                               │                             │
│  ┌──────────────┐            │                             │
│  │      S3      │◀───────────┘                             │
│  │   (README)   │                                          │
│  └──────────────┘                                          │
│         ▲                                                   │
│         │                                                   │
│  ┌──────┴───────┐                                          │
│  │  API Lambda  │                                          │
│  │ (API Gateway)│                                          │
│  └──────────────┘                                          │
└─────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Tech Stack

### Core Technologies

| Technology | Purpose | Version |
|------------|---------|---------|
| **Python** | Primary language |
| **FastAPI** | REST API framework | Latest |
| **PostgreSQL** | Primary database | 
| **pgvector** | Vector similarity search | Latest |
| **SQLAlchemy** | ORM | 2.0+ |
| **Alembic** | Database migrations | Latest |

### AI & ML

| Technology | Purpose |
|------------|---------|
| **Sentence Transformers** | Generate text embeddings |
| **all-mpnet-base-v2** | Embedding model (768 dimensions) |

### AWS Services

| Service | Purpose |
|---------|---------|
| **Lambda** | Serverless compute (API, Discoverer, Processor) |
| **API Gateway** | HTTP API endpoint |
| **SQS** | Message queue for processing |
| **DynamoDB** | State tracking for discovery |
| **S3** | README content storage |
| **RDS PostgreSQL** | Primary database with pgvector |
| **Parameter Store** | Configuration management |
| **CloudWatch** | Logging and monitoring |

### Additional Libraries

- **boto3**: AWS SDK
- **httpx**: Async HTTP client
- **beautifulsoup4**: HTML parsing
- **pydantic**: Data validation
- **mangum**: ASGI adapter for Lambda

---

## ✨ Features

### 🔍 Semantic Search
- Natural language queries (e.g., "machine learning frameworks for computer vision")
- Vector similarity search using cosine similarity
- AI-powered understanding of repository content

### 🎯 Advanced Filtering
- Filter by programming language
- Minimum star count
- Repository topics
- Combine multiple filters

### 📊 Rich Metadata
- Repository statistics (stars, forks, watchers, issues)
- Language breakdown
- Topics and tags
- Owner information
- Last update timestamps

### 🚀 Scalable Architecture
- Serverless components (auto-scaling)
- Asynchronous processing
- Efficient vector indexing (IVFFlat)
- S3 for large content storage

### 📈 Processing Pipeline
- Automatic repository discovery
- README extraction and cleaning
- Embedding generation
- Incremental updates
- Error handling and retry logic

---

## 📁 Project Structure

```
developer-archives/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI application entry point
│   ├── settings.py                # Configuration management
│   ├── db.py                      # Database connection
│   │
│   ├── api/                       # API layer
│   │   └── routes/
│   │       ├── search.py          # Search endpoints
│   │       └── repository.py      # Repository endpoints
│   │
│   ├── data_access/               # Data access layer
│   │   └── repositories/
│   │       ├── project_repository.py      # CRUD operations
│   │       ├── repository_detail.py       # Detail queries
│   │       └── search_repository.py       # Search queries
│   │
│   ├── external/                  # External service clients
│   │   ├── github_client.py       # GitHub API client
│   │   ├── embedding_client.py    # Embedding generation
│   │   └── s3_client.py           # S3 operations
│   │
│   ├── models/                    # SQLAlchemy models
│   │   └── project.py             # Project model
│   │
│   ├── schemas/                   # Pydantic schemas
│   │   ├── repository.py          # Repository schemas
│   │   └── search.py              # Search schemas
│   │
│   ├── services/                  # Business logic
│   │   ├── data_processing_service.py  # Processing logic
│   │   └── readme_extractor.py         # README extraction
│   │
│   └── tasks/                     # Lambda functions
│       ├── discoverer.py          # Repository discovery
│       └── processor.py           # Repository processing
│
├── alembic/                       # Database migrations
│   ├── versions/
│   │   ├── 3c3824bea299_create_initial_project_table.py
│   │   ├── 95babcc757cb_add_processing_status_to_projects.py
│   │   ├── e0bc7beba9b8_add_gin_index_for_topics.py
│   │   ├── e1020321b4e3_add_ivfflat_index_for_embeddings.py
│   │   └── faf9de66e450_add_s3_readme_storage_and_chunks.py
│   └── env.py
│
├── scripts/                       # Utility scripts
│   ├── check_db_stats.py
│   ├── check_processing_status.py
│   ├── fix_completed_status.py
│   ├── fix_failed_embeddings.py
│   └── manuel_ingest.py
│
├── lambda_deployers/              # Deployment scripts
│   ├── deploy_api.ps1
│   ├── deploy_discoverer_simple.ps1
│   └── deploy_processor_docker.ps1
│
├── Dockerfile.api                 # API Docker image
├── Dockerfile.processor           # Processor Docker image
├── Dockerfile.discoverer_builder  # Discoverer Docker image
├── requirements.txt               # Python dependencies
├── requirements-api.txt           # API-specific dependencies
├── requirements-processor.txt     # Processor-specific dependencies
└── alembic.ini                   # Alembic configuration
```

---

## 🚀 Setup & Installation

### Prerequisites

- Python 3.12+
- PostgreSQL 14+ with pgvector extension
- AWS Account (for deployment)
- GitHub Personal Access Token

### Local Development Setup

1. **Clone the repository**
```bash
git clone <repository-url>
cd developer-archives
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Set up PostgreSQL with pgvector**
```sql
CREATE DATABASE developer_archives;
\c developer_archives
CREATE EXTENSION vector;
```

5. **Create `.env` file**
```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=db_name
DB_USERNAME=your_username
DB_PASSWORD=your_password
GITHUB_API_TOKEN=your_github_token
AWS_REGION=your_aws_region
SQS_URL=your_sqs_url
DYNAMODB_TABLE_NAME=your_table_name
S3_README_BUCKET=your_bucket_name
```

6. **Run database migrations**
```bash
alembic upgrade head
```

7. **Start the API server**
```bash
python -m app.main
# or
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`

---

## 🔐 Environment Variables

### Database Configuration
- `DB_HOST`: PostgreSQL host
- `DB_PORT`: PostgreSQL port (default: 5432)
- `DB_NAME`: Database name
- `DB_USERNAME`: Database username
- `DB_PASSWORD`: Database password

### AWS Configuration
- `AWS_REGION`: AWS region (e.g., eu-central-1)
- `SQS_URL`: SQS queue URL for processing
- `DYNAMODB_TABLE_NAME`: DynamoDB table for state tracking
- `S3_README_BUCKET`: S3 bucket for README storage

### External Services
- `GITHUB_API_TOKEN`: GitHub Personal Access Token for API access

---


## 🌐 API Endpoints

### Base URL
```
Production: https://your-api-gateway-url.amazonaws.com/
Local: http://localhost:8000
```

### Search Endpoints

#### `GET /api/v1/search`
Semantic search for repositories

**Query Parameters:**
- `query` (required): Search query
- `language` (optional): Filter by programming language
- `min_stars` (optional): Minimum star count
- `topics` (optional): Filter by topics
- `page` (optional): Page number (default: 1)
- `page_size` (optional): Results per page (default: 12)

**Example:**
```bash
curl "https://api-url/api/v1/search?query=cloud+native+grpc+service&language=Go&min_stars=10000&page=1"
```

### Repository Endpoints

#### `GET /api/v1/projects/{project_id}`
Get detailed information about a specific repository

**Response:**
```json
{
  "id": 1,
  "github_id": 123456,
  "full_name": "user/repo",
  "description": "A machine learning library",
  "github_url": "https://github.com/user/repo",
  "stars": 5000,
  "forks": 1000,
  "watchers": 500,
  "open_issues": 50,
  "primary_language": "Python",
  "topics": ["machine-learning", "deep-learning"],
  "languages_breakdown": {
    "Python": 150000,
    "JavaScript": 50000
  },
  "owner_login": "user",
  "owner_avatar_url": "https://avatars.githubusercontent.com/...",
  "owner_url": "https://github.com/user",
  "created_at_github": "2020-01-01T00:00:00Z",
  "pushed_at_github": "2024-01-01T00:00:00Z",
  "updated_at_github": "2024-01-01T00:00:00Z"
}
```

#### `GET /api/v1/projects/{project_id}/readme`
Get README content for a repository

**Response:**
```
# Repository Title

Repository README content in markdown format...
```

---

## ☁️ AWS Deployment

### Architecture Components

1. **API Lambda + API Gateway**
   - FastAPI application wrapped with Mangum
   - HTTP API Gateway for routing
   - Deployed using Docker container

2. **Discoverer Lambda**
   - Scheduled execution (CloudWatch Events)
   - Discovers new repositories
   - Updates DynamoDB state
   - Sends messages to SQS

3. **Processor Lambda**
   - Triggered by SQS messages
   - Processes repositories
   - Generates embeddings
   - Stores in PostgreSQL and S3

### Deployment Steps

1. **Deploy API**
```powershell
cd lambda_deployers
.\deploy_api.ps1
```

2. **Deploy Discoverer**
```powershell
.\deploy_discoverer_simple.ps1
```

3. **Deploy Processor**
```powershell
.\deploy_processor_docker.ps1
```

### AWS Resources Required

- **Lambda Functions**: 3 (API, Discoverer, Processor)
- **API Gateway**: HTTP API
- **RDS**: PostgreSQL with pgvector
- **SQS**: Standard queue
- **DynamoDB**: On-demand table
- **S3**: Bucket for README storage
- **Parameter Store**: Configuration storage
- **CloudWatch**: Logs and monitoring
- **IAM**: Roles and policies

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **Sentence Transformers**: For the embedding model
- **pgvector**: For efficient vector similarity search
- **FastAPI**: For the excellent API framework
- **AWS**: For serverless infrastructure

---

## 📞 Contact

For questions or support, please open an issue on GitHub.

---

**Built with using Python, FastAPI, and AWS**

