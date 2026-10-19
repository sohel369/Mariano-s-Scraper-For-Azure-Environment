import os
import sys

# Delegate to build_verified_dataset for Mariano's
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts.build_verified_dataset import generate_verified_marianos_dataset

if __name__ == "__main__":
    generate_verified_marianos_dataset()
