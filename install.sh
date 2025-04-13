#!/bin/bash
# Stiebel Eltron Heat Pump Control - Installation Script
# This script installs the service, dependencies, and creates a systemd service

set -e  # Exit on any error

# Configuration variables
INSTALL_DIR="/opt/stiebel-control"
CONFIG_DIR="/etc/stiebel-control"
SERVICE_NAME="stiebel-control"
SERVICE_USER="$USER"
PYTHON_BIN="python3"

# Text formatting
BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"

# Helper functions
log_info() {
    echo -e "${GREEN}[INFO]${RESET} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${RESET} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${RESET} $1"
}

create_service_file() {
    cat > /tmp/stiebel-control.service << EOF
[Unit]
Description=Stiebel Eltron Heat Pump Control Service
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python -m stiebel_control.main --config $CONFIG_DIR/service_config.yaml
Restart=on-failure
RestartSec=5s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    log_error "Please run this script as root (use sudo)"
    exit 1
fi

# Display welcome message
echo -e "${BOLD}Stiebel Eltron Heat Pump Control - Installation Script${RESET}"
echo "This script will install the heat pump control service on your system."
echo 

# Check for system dependencies
log_info "Checking system dependencies..."
if ! command -v $PYTHON_BIN &> /dev/null; then
    log_error "Python 3 is not installed. Please install Python 3.9 or newer."
    exit 1
fi

if ! command -v ip &> /dev/null; then
    log_warn "The 'ip' command is not available. This might be needed for CAN interface setup."
fi

# Create installation directories
log_info "Creating installation directories..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$CONFIG_DIR"

# Copy application files
log_info "Copying application files..."
cp -r stiebel_control "$INSTALL_DIR/"
cp -r tools "$INSTALL_DIR/"
cp LICENSE README.md "$INSTALL_DIR/" 2>/dev/null || true

# Copy and adjust configuration files
log_info "Setting up configuration files..."
cp service_config.yaml "$CONFIG_DIR/"
cp entity_config.yaml "$CONFIG_DIR/" 2>/dev/null || true

# Create Python virtual environment
log_info "Creating Python virtual environment..."
$PYTHON_BIN -m venv "$INSTALL_DIR/venv"
source "$INSTALL_DIR/venv/bin/activate"

# Install Python dependencies
log_info "Installing Python dependencies..."
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -e "$INSTALL_DIR"
"$INSTALL_DIR/venv/bin/pip" install python-can paho-mqtt pyyaml

# Create systemd service
log_info "Creating systemd service..."
create_service_file
mv /tmp/stiebel-control.service /etc/systemd/system/

# Set permissions
log_info "Setting permissions..."
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
chown -R "$SERVICE_USER:$SERVICE_USER" "$CONFIG_DIR"
chmod -R 755 "$INSTALL_DIR"
chmod -R 644 "$CONFIG_DIR"/*

# Reload systemd and enable service
log_info "Enabling service..."
systemctl daemon-reload
systemctl enable "$SERVICE_NAME.service"

# Check if can0 interface exists
if ip link show can0 &> /dev/null; then
    log_info "Found CAN interface 'can0'"
else
    log_warn "CAN interface 'can0' not found. You need to configure it before starting the service."
    echo "You can configure it with commands like:"
    echo "  sudo ip link set can0 type can bitrate 20000"
    echo "  sudo ip link set up can0"
    echo "Consider adding these commands to /etc/network/interfaces or another startup script."
fi

# Final instructions
echo 
echo -e "${BOLD}Installation Complete!${RESET}"
echo 
echo "The service has been installed and enabled, but not started."
echo 
echo "Configuration files are located at: $CONFIG_DIR"
echo "You can start the service with: sudo systemctl start $SERVICE_NAME"
echo "You can check the service status with: sudo systemctl status $SERVICE_NAME"
echo "View logs with: sudo journalctl -u $SERVICE_NAME -f"
echo 
echo "Before starting, please review the configuration in $CONFIG_DIR/service_config.yaml"
echo "Ensure your CAN interface and MQTT settings are correct."
echo 

log_info "Thank you for installing Stiebel Eltron Heat Pump Control!"
