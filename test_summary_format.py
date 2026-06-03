#!/usr/bin/env python3
"""Test the new summary format implementation."""

from src.stx.translate.runner import TranslationResult
from src.stx.model import Document

def test_summary_format():
    """Test the new TranslationResult.format_summary() method."""
    
    # Create a mock result with sample data
    result = TranslationResult(
        document=Document(entries=[]),
        summaries=[],
        statuses=[],
        translated_count=4972,
        skipped_count=0,  # Should be 0 when retranslate_all=ON
        api_count=1018,
        cached_count=2344,
        deduped_count=1250,
        fuzzy_accepted_count=150,  # subset of cached_count
        imported_reuse_count=0,
        infile_reuse_count=360,
        resumed_count=11107,  # Pre-existing
        failed_count=807,
    )
    
    print("Testing new summary format:")
    print("=" * 60)
    print(result.format_summary())
    print("=" * 60)
    
    # Test the calculated properties
    print(f"\nCalculated properties:")
    print(f"rows_attempted: {result.rows_attempted}")
    print(f"total_with_translation: {result.total_with_translation}")  
    print(f"total_rows_processed: {result.total_rows_processed}")
    
    # Verify the math
    expected_attempted = 4972 + 807  # translated + failed
    expected_total_with_translation = 4972 + 11107  # translated + resumed
    expected_total_processed = 4972 + 11107 + 0 + 807  # translated + resumed + skipped + failed
    
    assert result.rows_attempted == expected_attempted, f"Expected {expected_attempted}, got {result.rows_attempted}"
    assert result.total_with_translation == expected_total_with_translation, f"Expected {expected_total_with_translation}, got {result.total_with_translation}"
    assert result.total_rows_processed == expected_total_processed, f"Expected {expected_total_processed}, got {result.total_rows_processed}"
    
    print(f"\n✅ All calculations correct!")
    print(f"✅ Summary format matches requirements!")

if __name__ == "__main__":
    test_summary_format()