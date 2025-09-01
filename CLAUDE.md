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

# Debug mode (with browser UI)
python main.py --list --no-headless --debug
```

### Mission URL Testing
```bash
python test_mission_urls.py       # Test mission URL parsing and access
```

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

### Configuration Management
Settings loaded from `.env` file with these key variables:
- `USERNAME`/`PASSWORD`: Game credentials (required)
- `DEFAULT_STRATEGY`: Deployment strategy (smart/balanced/minimum/optimal)
- `HEADLESS`: Browser display mode
- `LOG_LEVEL`: Logging verbosity
- `MAX_CONCURRENT_MISSIONS`: Safety limit for simultaneous operations

### Error Handling
- Retry mechanisms with exponential backoff
- DOM change detection with adaptive waiting  
- Comprehensive logging for debugging
- Graceful degradation on mission failures