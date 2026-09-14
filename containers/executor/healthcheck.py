#!/usr/bin/env python3
import sys
import requests
import os

def check_health():
    try:
        # Simple HTTP check
        response = requests.get('http://localhost:5000/health', timeout=3)
        if response.status_code == 200:
            print("Health check passed")
            sys.exit(0)  # Healthy
        else:
            print(f"Health check failed with status: {response.status_code}")
            sys.exit(1)  # Unhealthy
    except Exception as e:
        print(f"Health check failed with error: {e}")
        sys.exit(1)  # Unhealthy

if __name__ == '__main__':
    check_health()