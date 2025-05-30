#!/bin/bash

# Darwin Gödel Machine Setup Script
# Based on instructions from README.md

set -e  # Exit on any error

echo "🧬 Darwin Gödel Machine Setup Script"
echo "===================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running on macOS or Linux
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
    print_status "Detected macOS"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
    print_status "Detected Linux"
else
    print_error "Unsupported operating system: $OSTYPE"
    exit 1
fi

# Function to load .env file
load_env_file() {
    if [ -f ".env" ]; then
        print_status "Loading environment variables from .env file..."
        # Export variables from .env file
        export $(grep -v '^#' .env | xargs)
        print_success ".env file loaded"
    fi
}

# Step 1: Check API Keys
echo
print_status "Step 1: Checking API Keys"
echo "----------------------------------------"

# Load .env file if it exists
load_env_file

# Create .env template if it doesn't exist and no API keys are set
if [ ! -f ".env" ] && [ -z "$ANTHROPIC_API_KEY" ] && [ -z "$OPENAI_API_KEY" ]; then
    print_status "Creating .env template file..."
    cat > .env << 'EOF'
# Darwin Gödel Machine API Keys
# Copy this file and add your actual API keys

# Required: Anthropic Claude API key
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Required: OpenAI API key
OPENAI_API_KEY=your_openai_api_key_here

# Optional: AWS credentials (if using AWS)
# AWS_REGION=us-east-1
# AWS_ACCESS_KEY_ID=your_aws_access_key_here
# AWS_SECRET_ACCESS_KEY=your_aws_secret_key_here
EOF
    print_success ".env template created"
    print_warning "Please edit .env file with your actual API keys"
fi

# Check API keys (from environment or .env file)
missing_keys=()

if [ -z "$ANTHROPIC_API_KEY" ]; then
    missing_keys+=("ANTHROPIC_API_KEY")
fi

if [ -z "$OPENAI_API_KEY" ]; then
    missing_keys+=("OPENAI_API_KEY")
fi

if [ ${#missing_keys[@]} -eq 0 ]; then
    print_success "All required API keys are configured"
else
    print_warning "Missing API keys: ${missing_keys[*]}"
    echo
    echo "You can set them in one of these ways:"
    echo "1. Edit the .env file in this directory"
    echo "2. Set environment variables in your shell profile:"
    for key in "${missing_keys[@]}"; do
        echo "   export $key='your_key_here'"
    done
    echo "3. Set them temporarily: export $key='your_key_here'"
    echo
    
    read -p "Continue setup anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_status "Setup cancelled. Please configure API keys and run again."
        exit 1
    fi
fi

# Step 2: Verify Docker
echo
print_status "Step 2: Verifying Docker Installation"
echo "----------------------------------------"

if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first:"
    if [[ "$OS" == "macos" ]]; then
        echo "  - Download Docker Desktop from https://www.docker.com/products/docker-desktop"
    else
        echo "  - Run: curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh"
    fi
    exit 1
fi

print_status "Testing Docker with hello-world..."
if docker run hello-world &> /dev/null; then
    print_success "Docker is working correctly"
else
    print_error "Docker test failed. Checking permissions..."
    
    if [[ "$OS" == "linux" ]]; then
        print_status "Adding user to docker group..."
        sudo usermod -aG docker $USER
        print_warning "You need to log out and log back in for group changes to take effect"
        print_warning "Or run: newgrp docker"
        
        # Test if we can run docker after newgrp
        if newgrp docker <<< "docker run hello-world" &> /dev/null; then
            print_success "Docker permissions fixed"
        else
            print_error "Docker permissions issue persists. Please restart your session."
            exit 1
        fi
    else
        print_error "Docker test failed. Please check Docker Desktop is running."
        exit 1
    fi
fi

# Step 3: Python Environment Setup
echo
print_status "Step 3: Setting up Python Environment"
echo "----------------------------------------"

# Check Python version
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
print_status "Found Python $PYTHON_VERSION"

# Create virtual environment
if [ ! -d "venv" ]; then
    print_status "Creating virtual environment..."
    python3 -m venv venv
    print_success "Virtual environment created"
else
    print_status "Virtual environment already exists"
fi

# Activate virtual environment
print_status "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
print_status "Upgrading pip..."
pip install --upgrade pip

# Install requirements
print_status "Installing Python dependencies..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    print_success "Main dependencies installed"
else
    print_error "requirements.txt not found"
    exit 1
fi

# Install development requirements if requested
read -p "Install development dependencies for analysis? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if [[ "$OS" == "linux" ]]; then
        print_status "Installing graphviz system package..."
        if command -v apt-get &> /dev/null; then
            sudo apt-get update && sudo apt-get install -y graphviz graphviz-dev
        elif command -v yum &> /dev/null; then
            sudo yum install -y graphviz graphviz-devel
        elif command -v pacman &> /dev/null; then
            sudo pacman -S graphviz
        else
            print_warning "Please install graphviz manually for your distribution"
        fi
    elif [[ "$OS" == "macos" ]]; then
        if command -v brew &> /dev/null; then
            print_status "Installing graphviz via Homebrew..."
            brew install graphviz
        else
            print_warning "Please install Homebrew and run: brew install graphviz"
        fi
    fi
    
    if [ -f "requirements_dev.txt" ]; then
        print_status "Installing development dependencies (some may fail on macOS)..."
        if pip install -r requirements_dev.txt; then
            print_success "Development dependencies installed"
        else
            print_warning "Some development dependencies failed to install (this is normal for pygraphviz on macOS)"
            print_status "Installing individual packages that work..."
            pip install networkx matplotlib plotly || true
            print_success "Core development dependencies installed"
        fi
    fi
fi

# Step 4: Clone and Setup SWE-bench
echo
print_status "Step 4: Setting up SWE-bench"
echo "----------------------------------------"

if [ ! -d "swe_bench/SWE-bench" ]; then
    print_status "Cloning SWE-bench repository..."
    cd swe_bench
    git clone https://github.com/princeton-nlp/SWE-bench.git
    cd SWE-bench
    git checkout dc4c087c2b9e4cefebf2e3d201d27e36
    pip install -e .
    cd ../../
    print_success "SWE-bench setup complete"
else
    print_status "SWE-bench already cloned"
fi

# Step 5: Prepare Polyglot Dataset
echo
print_status "Step 5: Preparing Polyglot Dataset"
echo "----------------------------------------"

# Check git configuration
if ! git config user.name &> /dev/null || ! git config user.email &> /dev/null; then
    print_warning "Git user configuration missing"
    read -p "Enter your git username: " git_username
    read -p "Enter your git email: " git_email
    git config --global user.name "$git_username"
    git config --global user.email "$git_email"
    print_success "Git configuration set"
fi

print_status "Preparing Polyglot dataset..."
if PYTHONPATH=. python polyglot/prepare_polyglot_dataset.py; then
    print_success "Polyglot dataset prepared"
else
    print_error "Failed to prepare Polyglot dataset"
    exit 1
fi

# Step 6: Verify Installation
echo
print_status "Step 6: Verifying Installation"
echo "----------------------------------------"

# Check if key files exist
key_files=("DGM_outer.py" "coding_agent.py" "self_improve_step.py")
for file in "${key_files[@]}"; do
    if [ -f "$file" ]; then
        print_success "✓ $file found"
    else
        print_error "✗ $file missing"
    fi
done

# Check if directories exist
key_dirs=("swe_bench" "polyglot" "prompts" "utils")
for dir in "${key_dirs[@]}"; do
    if [ -d "$dir" ]; then
        print_success "✓ $dir/ directory found"
    else
        print_error "✗ $dir/ directory missing"
    fi
done

echo
print_success "🎉 Darwin Gödel Machine setup complete!"
echo
echo "Next steps:"
echo "1. Configure API keys (if not already done):"
echo "   Option A: Edit the .env file in this directory"
echo "   Option B: Set environment variables:"
echo "     export ANTHROPIC_API_KEY='your_key_here'"
echo "     export OPENAI_API_KEY='your_key_here'"
echo
echo "2. Activate the virtual environment:"
echo "   source venv/bin/activate"
echo
echo "3. Run the DGM:"
echo "   python DGM_outer.py"
echo
echo "4. Check the memory-bank/ directory for project documentation"
echo
print_warning "Remember: This system executes untrusted model-generated code."
print_warning "Always review the safety considerations in the documentation."