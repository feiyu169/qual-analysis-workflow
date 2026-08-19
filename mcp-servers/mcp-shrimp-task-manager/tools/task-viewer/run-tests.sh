#!/bin/bash

# Shrimp Task Viewer Test Runner
# This script provides convenient commands for running different test suites

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print colored output
print_message() {
    echo -e "${2}${1}${NC}"
}

# Function to show usage
show_usage() {
    echo "Shrimp Task Viewer Test Runner"
    echo ""
    echo "Usage: ./run-tests.sh [command] [options]"
    echo ""
    echo "Commands:"
    echo "  all              Run all tests"
    echo "  unit             Run unit tests only"
    echo "  integration      Run integration tests only"
    echo "  component        Run React component tests only"
    echo "  server           Run server tests only"
    echo "  edge             Run edge case tests only"
    echo "  coverage         Run tests with coverage report"
    echo "  watch            Run tests in watch mode"
    echo "  ui               Run tests with UI interface"
    echo "  specific <file>  Run specific test file"
    echo "  help             Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./run-tests.sh all"
    echo "  ./run-tests.sh coverage"
    echo "  ./run-tests.sh specific src/test/App.test.jsx"
}

# Check if npm packages are installed
check_dependencies() {
    if [ ! -d "node_modules" ]; then
        print_message "Installing dependencies..." "$YELLOW"
        npm install
    fi
}

# Main command handling
case "$1" in
    all)
        check_dependencies
        print_message "Running all tests..." "$GREEN"
        npm test -- --run
        ;;
    
    unit)
        check_dependencies
        print_message "Running unit tests..." "$GREEN"
        npm test -- --run src/test/
        ;;
    
    integration)
        check_dependencies
        print_message "Running integration tests..." "$GREEN"
        npm test -- --run test/integration.test.js
        ;;
    
    component)
        check_dependencies
        print_message "Running React component tests..." "$GREEN"
        npm test -- --run src/test/
        ;;
    
    server)
        check_dependencies
        print_message "Running server tests..." "$GREEN"
        npm test -- --run test/server.test.js
        ;;
    
    edge)
        check_dependencies
        print_message "Running edge case tests..." "$GREEN"
        npm test -- --run test/edge-cases.test.js
        ;;
    
    coverage)
        check_dependencies
        print_message "Running tests with coverage..." "$GREEN"
        npm test -- --coverage --config vitest.config.coverage.js
        print_message "\nCoverage report generated in ./coverage/" "$YELLOW"
        ;;
    
    watch)
        check_dependencies
        print_message "Running tests in watch mode..." "$GREEN"
        npm test -- --watch
        ;;
    
    ui)
        check_dependencies
        print_message "Starting test UI..." "$GREEN"
        npm run test:ui
        ;;
    
    specific)
        if [ -z "$2" ]; then
            print_message "Error: Please specify a test file" "$RED"
            echo "Example: ./run-tests.sh specific src/test/App.test.jsx"
            exit 1
        fi
        check_dependencies
        print_message "Running specific test: $2" "$GREEN"
        npm test -- --run "$2"
        ;;
    
    help|--help|-h)
        show_usage
        ;;
    
    *)
        if [ -z "$1" ]; then
            # No arguments, run all tests
            check_dependencies
            print_message "Running all tests..." "$GREEN"
            npm test -- --run
        else
            print_message "Error: Unknown command '$1'" "$RED"
            echo ""
            show_usage
            exit 1
        fi
        ;;
esac

# Check exit status
if [ $? -eq 0 ]; then
    print_message "\n✅ Tests completed successfully!" "$GREEN"
else
    print_message "\n❌ Tests failed!" "$RED"
    exit 1
fi