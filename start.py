#!/usr/bin/env python
"""
Quick start script for Solar Quotation System
Run this file to start the application
"""

import os
import sys
import subprocess

def check_requirements():
    """Check if requirements are installed"""
    try:
        import fastapi
        import uvicorn
        import jinja2
        return True
    except ImportError:
        return False

def main():
    print("=" * 60)
    print("Solar Quotation System - Quick Start")
    print("=" * 60)
    print()

    # Check if requirements are installed
    if not check_requirements():
        print("[!] Dependencies not installed!")
        print()
        print("Installing dependencies...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print()

    # Check if database exists
    if not os.path.exists("solar_quotes.db"):
        print("[*] Initializing database...")
        from database import init_database
        init_database()
        print()

    # Start the application
    print("[*] Starting Solar Quotation System...")
    print()
    print("=" * 60)
    print("[URL] Application URL: http://localhost:8000")
    print("[LOGIN] Default Login:")
    print("   Email: admin@solar.com")
    print("   Password: admin123")
    print("=" * 60)
    print()
    print("Press Ctrl+C to stop the server")
    print()

    # Run uvicorn
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nSolar Quotation System stopped. Goodbye!")
        sys.exit(0)
