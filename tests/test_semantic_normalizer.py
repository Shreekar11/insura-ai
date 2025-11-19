"""Simple standalone test for semantic normalizer (no API calls required)."""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.ocr.semantic_normalizer import SemanticNormalizer


def test_semantic_normalizer():
    """Test semantic normalizer functionality."""
    print("=" * 70)
    print("Testing Semantic Normalizer")
    print("=" * 70)
    
    normalizer = SemanticNormalizer()
    
    # Test date normalization
    print("\n📅 Date Normalization Tests:")
    print("-" * 70)
    test_dates = [
        ("12th Dec 2023", "2023-12-12"),
        ("12/25/2023", "2023-12-25"),
        ("Dec 25, 2023", "2023-12-25"),
        ("01/15/24", "2024-01-15"),
    ]
    
    for input_date, expected in test_dates:
        result = normalizer.normalize_date(input_date)
        status = "✅" if result == expected else "❌"
        print(f"{status} {input_date:25} → {result:15} (expected: {expected})")
    
    # Test amount normalization
    print("\n💰 Amount Normalization Tests:")
    print("-" * 70)
    test_amounts = [
        ("₹1,20,000", 120000.0),
        ("Rs. 12,500/-", 12500.0),
        ("$500.00", 500.0),
        ("25,00,000.00", 2500000.0),
    ]
    
    for input_amount, expected in test_amounts:
        result = normalizer.normalize_amount(input_amount)
        status = "✅" if result == expected else "❌"
        print(f"{status} {input_amount:25} → {result:15} (expected: {expected})")
    
    # Test percentage normalization
    print("\n📊 Percentage Normalization Tests:")
    print("-" * 70)
    test_percentages = [
        ("75 %", "75%"),
        ("$75 \\%$", "75%"),
        ("75 percent", "75%"),
        ("12.5%", "12.5%"),
    ]
    
    for input_pct, expected in test_percentages:
        result = normalizer.normalize_percentage(input_pct)
        status = "✅" if result == expected else "❌"
        print(f"{status} {input_pct:25} → {result:15} (expected: {expected})")
    
    # Test policy number normalization
    print("\n🔢 Policy Number Normalization Tests:")
    print("-" * 70)
    test_policies = [
        ("pol 12345-a", "POL12345-A"),
        ("POL-12345-A", "POL-12345-A"),
        ("pol  12345  a", "POL12345A"),
    ]
    
    for input_policy, expected in test_policies:
        result = normalizer.normalize_policy_number(input_policy)
        status = "✅" if result == expected else "❌"
        print(f"{status} {input_policy:25} → {result:15} (expected: {expected})")
    
    # Test name normalization
    print("\n👤 Name Normalization Tests:")
    print("-" * 70)
    test_names = [
        ("john  doe", "John Doe"),
        ("JANE SMITH", "Jane Smith"),
        ("mary-ann jones", "Mary-Ann Jones"),
    ]
    
    for input_name, expected in test_names:
        result = normalizer.normalize_name(input_name)
        status = "✅" if result == expected else "❌"
        print(f"{status} {input_name:25} → {result:15} (expected: {expected})")
    
    # Test email normalization
    print("\n📧 Email Normalization Tests:")
    print("-" * 70)
    test_emails = [
        ("John.Doe@Example.COM", "john.doe@example.com"),
        ("JANE@COMPANY.ORG", "jane@company.org"),
    ]
    
    for input_email, expected in test_emails:
        result = normalizer.normalize_email(input_email)
        status = "✅" if result == expected else "❌"
        print(f"{status} {input_email:25} → {result:25} (expected: {expected})")
    
    # Test text with fields extraction
    print("\n📄 Text Field Extraction Test:")
    print("-" * 70)
    sample_text = """
    Policy Number: POL-12345-A
    Effective Date: 12th Dec 2023
    Expiry Date: 12/12/2024
    Premium Amount: ₹1,20,000/-
    Coverage: 75%
    Contact: john.doe@example.com
    """
    
    result = normalizer.normalize_text_with_fields(sample_text)
    
    print(f"✅ Dates extracted: {len(result['extracted_fields']['dates'])}")
    for date in result['extracted_fields']['dates']:
        print(f"   - {date['original']:20} → {date['normalized']}")
    
    print(f"✅ Amounts extracted: {len(result['extracted_fields']['amounts'])}")
    for amount in result['extracted_fields']['amounts']:
        print(f"   - {amount['original']:20} → {amount['normalized']}")
    
    print(f"✅ Emails extracted: {len(result['extracted_fields']['emails'])}")
    for email in result['extracted_fields']['emails']:
        print(f"   - {email['original']:30} → {email['normalized']}")
    
    print("\n" + "=" * 70)
    print("✅ All semantic normalizer tests completed!")
    print("=" * 70)


if __name__ == "__main__":
    test_semantic_normalizer()
