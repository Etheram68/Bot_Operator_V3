# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Environment Setup

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Configure environment
cp .env.example .env
# Edit .env with your credentials
```

### Testing and Development

```bash
# Architecture testing
python test_architecture.py        # Full architecture test
python test_smart_strategy.py      # Test intelligent deployment strategy
python quick_test.py              # Quick connection test

# Run main application
python main.py --list             # List available missions
python main.py --mission 12345    # Deploy specific mission
python main.py --auto --max-missions 3  # Auto deploy (max 3)
python main.py --continuous       # Continuous mode
python main.py --status          # Show bot status

# Mission conditions analysis and knowledge base enrichment
python main.py --analyze-conditions                    # Analyze conditions of available missions
python main.py --analyze-conditions --max-analyze 10   # Analyze up to 10 missions
python main.py --analyze-mission 12345                 # Analyze conditions of specific mission
python main.py --test-mission 12345                    # Test complete mission scraping (patients, requirements)

# Debug mode (with browser UI)
python main.py --list --no-headless --debug

# Pattern analysis for unrecognized vehicles
python bot_operateur/utils/analyze_patterns.py    # Analyze unrecognized vehicle patterns
```

### Mission URL Testing

```bash
python test_mission_urls.py       # Test mission URL parsing and access
```

## Docker Deployment

### Quick Start with Docker

```bash
# Build and run with credentials
docker-compose up --build -d

# Or using docker run directly
docker run -d \
  -e USERNAME=your_username \
  -e PASSWORD=your_password \
  -v $(pwd)/data:/app/data \
  bot-operateur:latest python main.py --continuous
```

### QNAP NAS Deployment

1. Connect to your QNAP via SSH
2. Transfer project files to NAS
3. Create `.env` file with your credentials:

```bash
USERNAME=your_operateur112_username
PASSWORD=your_operateur112_password
DEFAULT_STRATEGY=smart
HEADLESS=true
LOG_LEVEL=INFO
```

4. Deploy using docker-compose:

```bash
# Build and start
docker-compose up --build -d

# View logs
docker-compose logs -f bot-operateur

# Stop
docker-compose down
```

### Docker Commands

```bash
# Build image
docker build -t bot-operateur:latest .

# Run with custom command
docker run -it --rm \
  -e USERNAME=user -e PASSWORD=pass \
  bot-operateur:latest python main.py --list

# Monitor container
docker stats bot-operateur-112
docker logs -f bot-operateur-112

# Access container shell
docker exec -it bot-operateur-112 /bin/bash
```

### Persistent Data

Data is stored in `./data/` directory with subdirectories:

- `logs/`: Application logs
- `cache/`: Browser cache and temporary files
- `config/`: Custom configuration files
- `bot_data/`: Mission data and analytics

## Architecture Overview

This is a Python automation bot for the "Opérateur 112" emergency management game, built with:

- **Playwright** for browser automation
- **Pydantic** for configuration and data models
- **Loguru** for structured logging
- **AsyncIO** for concurrent operations

### Core Components

#### Main Entry Point

- `main.py`: CLI interface with argument parsing and execution modes
- `bot_operateur/`: Main package containing all bot functionality

#### Core System (`bot_operateur/core/`)

- `bot.py`: Main `OperateurBot` class - coordinates all components
- `browser_manager.py`: Handles Playwright browser lifecycle and page navigation
- `mission_manager.py`: Orchestrates mission detection, analysis, and deployment

#### Data Models (`bot_operateur/models/`)

- `mission.py`: Mission data structure and validation
- `vehicle.py`: Vehicle information and capabilities
- `patient.py`: Patient data and medical requirements
- `requirement_parser.py`: Intelligent parsing of mission requirements

#### Web Scrapers (`bot_operateur/scrapers/`)

- `mission_scraper.py`: Extracts missions from game interface
- `vehicle_scraper.py`: Gathers available vehicle information
- `patient_scraper.py`: Collects patient data from missions

#### Deployment Strategies (`bot_operateur/strategies/`)

- `smart_strategy.py`: AI-powered vehicle selection with game data integration
- `balanced_strategy.py`: Safety-focused deployment with margins
- `minimum_strategy.py`: Cost-optimized minimal deployment
- `optimal_strategy.py`: Performance-based vehicle selection

#### Configuration (`bot_operateur/config/`)

- `settings.py`: Pydantic-based configuration with environment variable support

#### Utilities (`bot_operateur/utils/`)

- `analyze_patterns.py`: Pattern analysis tool for unrecognized vehicle types
- `logger.py`: Logging configuration and setup utilities
- `retry.py`: Retry mechanisms with exponential backoff
- `dom_utils.py`: DOM manipulation and waiting utilities

### Key Architecture Patterns

1. **Async Context Manager Pattern**: `OperateurBot` uses `async with` for proper resource cleanup
2. **Strategy Pattern**: Multiple deployment strategies with shared interface
3. **Scraper Pattern**: Specialized scrapers for different data types
4. **Settings from Environment**: All configuration via `.env` file with validation

### Data Flow

1. Browser connects and authenticates via `browser_manager`
2. `mission_scraper` detects available missions
3. `mission_manager` analyzes requirements using `requirement_parser`
4. Selected strategy determines optimal vehicle deployment
5. `browser_manager` executes deployment actions
6. Results logged and returned via structured response

### Smart Strategy Intelligence

The recommended "smart" strategy includes:

- Real vehicle recognition from `needs_labels_v2.json` and `vehicles_v2.json`
- Automatic fallback alternatives (VSAV → ASSU → Ambulance)
- Proximity-based selection (first found = closest)
- Adaptive complexity handling (simple → major incident)
- Personnel-to-vehicle conversion (4 Spécialistes IMP → 1 VIMP based on crew_size)
- Multi-need satisfaction (1 FS vehicle can satisfy both VTU and VSR requirements)
- Already-deployed vehicle tracking to avoid over-deployment

### Configuration Management

Settings loaded from `.env` file with these key variables:

- `USERNAME`/`PASSWORD`: Game credentials (required)
- `DEFAULT_STRATEGY`: Deployment strategy (smart/balanced/minimum/optimal)
- `HEADLESS`: Browser display mode
- `LOG_LEVEL`: Logging verbosity
- `MAX_CONCURRENT_MISSIONS`: Safety limit for simultaneous operations
- `MIN_CREDITS_THRESHOLD`: Minimum mission credits to consider
- `PAGE_LOAD_TIMEOUT`/`ELEMENT_WAIT_TIMEOUT`: Browser timing controls

### Error Handling

- Retry mechanisms with exponential backoff
- DOM change detection with adaptive waiting
- Comprehensive logging for debugging
- Graceful degradation on mission failures

## Key Implementation Details

### Requirement Parser Intelligence

The `requirement_parser.py` uses sophisticated text parsing:

- HTML table structure recognition for mission requirements
- Context-aware quantity extraction (handles "Fourgons d'incendie requis: 2")
- Personnel-to-vehicle conversion using `vehicle_specs.crew_size`
- Generic requirement types (CARS_POLICE) that allow proximity-based vehicle selection

### Vehicle Selection Logic

The `vehicle_scraper.py` implements intelligent selection:

- Already-deployed vehicle detection and adjustment from mission tables
- Multi-alternative satisfaction (one FS vehicle satisfies both VTU and VSR needs)
- Proximity-based selection (vehicles listed first are closest)
- Alternative mapping resolution (VTU → FS, AMBULANCE → VSAV/ASSU/SMUR(A))

### Mission Processing Flow

1. Parse mission text → extract generic requirements (e.g., CARS_POLICE: 15)
2. Convert personnel needs → vehicles (4 Spécialistes IMP → 1 VIMP)
3. Check already deployed vehicles → adjust requirements
4. Select closest available vehicles using alternatives mapping
5. Deploy and track selected vehicles

### Data File Dependencies

- `needs_labels_v2.json`: Regex patterns matching mission text to vehicle types
- `vehicles_v2.json`: Vehicle alternatives and crew specifications
- Both files are critical for the smart strategy's operation
