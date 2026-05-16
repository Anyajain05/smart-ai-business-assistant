#!/usr/bin/env python
"""
Quick start script for Smart AI Business Assistant
Demonstrates the complete workflow in one go
"""

import subprocess
import sys
import os
import time

def run_command(cmd, description):
    """Run command and print status"""
    print(f"\n{'='*60}")
    print(f"[*] {description}")
    print(f"{'='*60}")
    print(f"Running: {cmd}\n")
    
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"ERROR: Command failed with exit code {result.returncode}")
        return False
    return True

def main():
    print("\n")
    print("  ╔══════════════════════════════════════════════════════╗")
    print("  ║  Smart AI Business Assistant - Quick Start Guide     ║")
    print("  ║  Production-Ready MVP for SME Operations             ║")
    print("  ╚══════════════════════════════════════════════════════╝")
    
    # Check Python version
    if sys.version_info < (3, 12):
        print("\n⚠️  Python 3.12+ required. Please upgrade.")
        sys.exit(1)
    
    print(f"\n✓ Python version: {sys.version.split()[0]}")
    
    # Step 1: Create venv
    print("\n\n[1/6] SETUP PYTHON ENVIRONMENT")
    print("-" * 60)
    if not os.path.exists(".venv"):
        if not run_command("python -m venv .venv", "Creating virtual environment"):
            sys.exit(1)
    else:
        print("✓ Virtual environment already exists")
    
    # Step 2: Install requirements
    print("\n[2/6] INSTALL DEPENDENCIES")
    print("-" * 60)
    if os.name == 'nt':  # Windows
        pip_cmd = ".venv\\Scripts\\pip"
    else:  # Unix
        pip_cmd = ".venv/bin/pip"
    
    if not run_command(f"{pip_cmd} install -r requirements.txt", "Installing packages"):
        sys.exit(1)
    
    # Step 3: Setup environment
    print("\n[3/6] CONFIGURE ENVIRONMENT")
    print("-" * 60)
    if not os.path.exists(".env"):
        if os.name == 'nt':
            run_command("copy .env.example .env", "Copying environment template")
        else:
            run_command("cp .env.example .env", "Copying environment template")
    else:
        print("✓ .env file already exists")
    
    # Step 4: Initialize database
    print("\n[4/6] DATABASE SETUP")
    print("-" * 60)
    print("✓ Database will auto-initialize on server start")
    print("  Location: data/app.db")
    print("  Tables: users, conversations, messages, leads, documents, etc.")
    
    # Step 5: Show info
    print("\n[5/6] PROJECT STRUCTURE")
    print("-" * 60)
    print("""
    app/
      ├── api/routes.py          ← REST endpoints
      ├── services/
      │   ├── assistant.py       ← Chat + memory
      │   ├── agents.py          ← Multi-agent orchestration
      │   ├── leads.py           ← Lead extraction
      │   ├── automations.py     ← Workflows
      │   └── rag.py             ← Document retrieval
      ├── core/
      │   ├── db.py              ← Database schema
      │   └── security.py        ← JWT + passwords
      ├── templates/index.html   ← Dashboard UI
      └── static/
          ├── app.js             ← Frontend logic
          └── styles.css         ← Styling
    """)
    
    # Step 6: Ready to start
    print("\n[6/6] READY TO START")
    print("-" * 60)
    print("""
    ✓ All setup complete!
    
    To start the server, run:
    
    Windows:
      .venv\\Scripts\\activate
      python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
    
    macOS/Linux:
      source .venv/bin/activate
      python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
    
    Then open your browser to:
      http://127.0.0.1:8000
    
    Demo Login:
      Email:    admin@example.com
      Password: admin123
    
    Next Steps:
      1. Sign in with demo credentials
      2. Upload a document from "data/" folder
      3. Chat with the assistant to capture a lead
      4. View leads and analytics
      5. Run automations from the workflows tab
    """)
    
    print("\n" + "="*60)
    print("For full documentation, see README.md")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
