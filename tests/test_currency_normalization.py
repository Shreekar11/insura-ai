#!/usr/bin/env python3
"""Test enhanced currency normalization with ISO 4217 codes and spelled-out numbers."""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.normalization.semantic_normalizer import SemanticNormalizer


def test_currency_normalization():
    """Test enhanced currency normalization."""
    
    normalizer = SemanticNormalizer()
    
    print("=" * 80)
    print("ENHANCED CURRENCY NORMALIZATION TEST")
    print("=" * 80)
    
    # Test 1: Symbol-based currencies
    print("\n💰 Symbol-Based Currency Tests:")
    print("-" * 80)
    test_cases = [
        ("$1,200.50", {"amount": 1200.50, "currency": "USD"}),
        ("€50.50", {"amount": 50.50, "currency": "EUR"}),
        ("£20", {"amount": 20.0, "currency": "GBP"}),
        ("₹1,20,000", {"amount": 120000.0, "currency": "INR"}),
        ("Rs. 12,500/-", {"amount": 12500.0, "currency": "INR"}),
    ]
    
    for input_str, expected in test_cases:
        result = normalizer.normalize_currency(input_str)
        match = result == expected if result else False
        status = "✅" if match else "❌"
        print(f"{status} {input_str:20} → {result}")
        if not match:
            print(f"   Expected: {expected}")
    
    # Test 2: ISO code format
    print("\n🌍 ISO Code Format Tests:")
    print("-" * 80)
    test_cases = [
        ("USD 100", {"amount": 100.0, "currency": "USD"}),
        ("EUR 50.50", {"amount": 50.50, "currency": "EUR"}),
        ("GBP 20", {"amount": 20.0, "currency": "GBP"}),
        ("100 USD", {"amount": 100.0, "currency": "USD"}),
    ]
    
    for input_str, expected in test_cases:
        result = normalizer.normalize_currency(input_str)
        match = result == expected if result else False
        status = "✅" if match else "❌"
        print(f"{status} {input_str:20} → {result}")
        if not match:
            print(f"   Expected: {expected}")
    
    # Test 3: Spelled-out numbers
    print("\n📝 Spelled-Out Number Tests:")
    print("-" * 80)
    test_cases = [
        ("fifty dollars", {"amount": 50.0, "currency": "USD"}),
        ("one hundred euros", {"amount": 100.0, "currency": "EUR"}),
        ("twenty pounds", {"amount": 20.0, "currency": "GBP"}),
        ("two lakh rupees", {"amount": 200000.0, "currency": "INR"}),
    ]
    
    for input_str, expected in test_cases:
        result = normalizer.normalize_currency(input_str)
        match = result == expected if result else False
        status = "✅" if match else "❌"
        print(f"{status} {input_str:25} → {result}")
        if not match:
            print(f"   Expected: {expected}")
    
    # Test 4: Text normalization with field extraction
    print("\n📄 Text Normalization with Currency Extraction:")
    print("-" * 80)
    
    sample_text = """
    Insurance Policy Details:
    - Premium: Rs. 1,500/-
    - Coverage: $50,000
    - Deductible: €500
    - Claim Amount: fifty thousand dollars
    - Policy Fee: 100 USD
    """
    
    result = normalizer.normalize_text_with_fields(sample_text)
    
    print("\nOriginal Text:")
    print(sample_text)
    
    print("\nNormalized Text:")
    print(result["normalized_text"])
    
    print(f"\n💰 Amounts Extracted: {len(result['extracted_fields']['amounts'])}")
    for item in result['extracted_fields']['amounts']:
        print(f"   • {item['original']:30} → {item['normalized']}")
    
    print("\n" + "=" * 80)
    print("✅ ENHANCED CURRENCY NORMALIZATION TEST COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    test_currency_normalization()
