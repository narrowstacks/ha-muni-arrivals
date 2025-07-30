#!/bin/bash

# Installation script for Muni Times Home Assistant integration

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Muni Times Home Assistant Integration Installer${NC}"
echo "=============================================="

# Check if we're in the right directory
if [ ! -f "manifest.json" ]; then
    echo -e "${RED}Error: manifest.json not found. Please run this script from the integration directory.${NC}"
    exit 1
fi

# Get Home Assistant config directory
if [ -z "$1" ]; then
    echo -e "${YELLOW}Please provide your Home Assistant config directory path:${NC}"
    echo "Example: ./install.sh /config"
    echo "Example: ./install.sh ~/.homeassistant"
    read -p "Home Assistant config path: " HA_CONFIG_DIR
else
    HA_CONFIG_DIR="$1"
fi

# Verify Home Assistant config directory exists
if [ ! -d "$HA_CONFIG_DIR" ]; then
    echo -e "${RED}Error: Home Assistant config directory '$HA_CONFIG_DIR' not found.${NC}"
    exit 1
fi

# Create custom_components directory if it doesn't exist
CUSTOM_COMPONENTS_DIR="$HA_CONFIG_DIR/custom_components"
if [ ! -d "$CUSTOM_COMPONENTS_DIR" ]; then
    echo -e "${YELLOW}Creating custom_components directory...${NC}"
    mkdir -p "$CUSTOM_COMPONENTS_DIR"
fi

# Create the integration directory
INTEGRATION_DIR="$CUSTOM_COMPONENTS_DIR/muni_times"
if [ -d "$INTEGRATION_DIR" ]; then
    echo -e "${YELLOW}Existing installation found. Backing up...${NC}"
    mv "$INTEGRATION_DIR" "$INTEGRATION_DIR.backup.$(date +%Y%m%d_%H%M%S)"
fi

echo -e "${YELLOW}Installing Muni Times integration...${NC}"
mkdir -p "$INTEGRATION_DIR"

# Copy files
cp manifest.json "$INTEGRATION_DIR/"
cp __init__.py "$INTEGRATION_DIR/"
cp const.py "$INTEGRATION_DIR/"
cp config_flow.py "$INTEGRATION_DIR/"
cp sensor.py "$INTEGRATION_DIR/"
cp muni_api.py "$INTEGRATION_DIR/"
cp strings.json "$INTEGRATION_DIR/"

echo -e "${GREEN}Installation completed!${NC}"
echo ""
echo "Next steps:"
echo "1. Restart Home Assistant"
echo "2. Go to Settings > Devices & Services"
echo "3. Click 'Add Integration' and search for 'Muni Times'"
echo "4. Follow the configuration wizard"
echo ""
echo "You'll need:"
echo "- A 511.org API key (get one at https://511.org/developers/)"
echo "- Transit stop codes for your desired stops"
echo ""
echo -e "${YELLOW}For help finding stop codes and configuration examples, see:${NC}"
echo "- README.md"
echo "- example_configuration.yaml"