#!/usr/bin/env python3
"""Test script for semantic normalization integration.

This script tests the two-stage normalization pipeline:
1. LLM normalization (structural cleanup)
2. Semantic normalization (field-level accuracy)
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.normalization.semantic_normalizer import SemanticNormalizer


def test_semantic_normalizer():
    """Test semantic normalizer with sample insurance text."""
    
    normalizer = SemanticNormalizer()
    
    # Sample text with various fields (simulating LLM output)
    sample_text = """
    Policy Details:
    - Policy Number: POL 12345-A
    - Issue Date: 12/12/2023
    - Expiry Date: Dec 12, 2024
    - Premium Amount: Rs. 1,500/-
    - Coverage Limit: ₹25,00,000
    - Contact Email: customer@insurance.com
    - Claim Amount: USD $5,000.00
    """
    
    print("=" * 80)
    print("SEMANTIC NORMALIZATION TEST")
    print("=" * 80)
    print("\nOriginal Text:")
    print("-" * 80)
    print(sample_text)
    
    # Apply semantic normalization
    result = normalizer.normalize_text_with_fields(sample_text)
    
    print("\n" + "=" * 80)
    print("NORMALIZED TEXT:")
    print("=" * 80)
    print(result["normalized_text"])
    
    print("\n" + "=" * 80)
    print("EXTRACTED FIELDS:")
    print("=" * 80)
    
    fields = result["extracted_fields"]
    
    print(f"\n📅 Dates Found: {len(fields['dates'])}")
    for item in fields["dates"]:
        print(f"   • {item['original']} → {item['normalized']}")
    
    print(f"\n💰 Amounts Found: {len(fields['amounts'])}")
    for item in fields["amounts"]:
        print(f"   • {item['original']} → {item['normalized']}")
    
    print(f"\n📧 Emails Found: {len(fields['emails'])}")
    for item in fields["emails"]:
        print(f"   • {item['original']} → {item['normalized']}")
    
    print("\n" + "=" * 80)
    print("✅ TEST COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    test_semantic_normalizer()
