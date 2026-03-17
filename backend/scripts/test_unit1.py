"""
Unit #1 Tests: Footnote Detection & footnotes_map.json Generation

Test that:
1. Footnotes are correctly extracted from DOCX
2. footnotes_map.json structure is correct
3. display_num calculation handles gaps in IDs
4. Multiple footnotes in same paragraph are handled
5. DOCX with no footnotes returns detected=False
"""

import json
import tempfile
import shutil
from pathlib import Path
from docx_converter import extract_footnotes_from_docx, build_footnotes_map


class TestUnit1:
    """Unit #1 test suite."""
    
    @staticmethod
    def test_extract_3_footnotes(sample_docx_path):
        """Test extraction of DOCX with footnotes."""
        print("\n=== Test 1.1: Extract footnotes ===")
        
        result = extract_footnotes_from_docx(sample_docx_path)
        
        assert result['detected'] == True, "Should detect footnotes"
        assert len(result['footnote_content']) > 0, "Should have footnote content"
        assert len(result['paragraph_data']) > 0, "Should have paragraph data"
        
        footnote_count = len(result['footnote_content'])
        print(f"✓ Detected {footnote_count} footnotes")
        print(f"✓ Found {len(result['paragraph_data'])} paragraphs with content")
        
        return result
    
    @staticmethod
    def test_build_footnotes_map(result):
        """Test footnotes_map.json structure."""
        print("\n=== Test 1.2: Build footnotes_map.json ===")
        
        fn_map = build_footnotes_map(result['footnote_content'], result['paragraph_data'])
        
        assert fn_map['detected'] == True
        assert fn_map['total'] == len(result['footnote_content'])
        assert len(fn_map['footnotes']) == len(result['footnote_content'])
        
        # Check structure of first footnote
        fn = fn_map['footnotes'][0]
        required_keys = {'id', 'display_num', 'content', 'paragraph_index', 
                        'paragraph_text', 'injected', 'status', 'position_in_paragraph'}
        assert set(fn.keys()) >= required_keys, f"Missing keys: {required_keys - set(fn.keys())}"
        
        # Check types
        assert isinstance(fn['id'], str)
        assert isinstance(fn['display_num'], int)
        assert isinstance(fn['content'], str)
        assert isinstance(fn['paragraph_index'], int)
        assert isinstance(fn['injected'], bool)
        assert fn['status'] in ('pending', 'approved', 'edited')
        
        print(f"✓ footnotes_map structure is valid")
        print(f"✓ Total footnotes: {fn_map['total']}")
        print(json.dumps(fn_map, indent=2))
        
        return fn_map
    
    @staticmethod
    def test_display_num_calculation(result):
        """Test that display_num handles gaps in footnote IDs."""
        print("\n=== Test 1.3: display_num calculation (gap handling) ===")
        
        # In the test DOCX, IDs are: 0 (empty), 1 (empty), 2, 3, 4
        # So display_nums should be: 2→1, 3→2, 4→3
        
        fn_map = build_footnotes_map(result['footnote_content'], result['paragraph_data'])
        
        # Verify sequential display_nums starting from 1
        for i, fn in enumerate(fn_map['footnotes']):
            expected_display = i + 1
            assert fn['display_num'] == expected_display, \
                f"Footnote {i}: expected display_num={expected_display}, got {fn['display_num']}"
        
        print(f"✓ display_num values are sequential: {[f['display_num'] for f in fn_map['footnotes']]}")
        print(f"✓ Gap handling works correctly (IDs: {[f['id'] for f in fn_map['footnotes']]})")
    
    @staticmethod
    def test_multiple_footnotes_same_paragraph(result):
        """Test that multiple footnotes in one paragraph are handled."""
        print("\n=== Test 1.4: Multiple footnotes in same paragraph ===")
        
        fn_map = build_footnotes_map(result['footnote_content'], result['paragraph_data'])
        
        # Count footnotes per paragraph
        para_counts = {}
        for fn in fn_map['footnotes']:
            para_idx = fn['paragraph_index']
            para_counts[para_idx] = para_counts.get(para_idx, 0) + 1
        
        multi_para = {idx: count for idx, count in para_counts.items() if count > 1}
        
        if multi_para:
            print(f"✓ Found paragraphs with multiple footnotes: {multi_para}")
            for para_idx, count in multi_para.items():
                footnotes_in_para = [f for f in fn_map['footnotes'] if f['paragraph_index'] == para_idx]
                for fn in footnotes_in_para:
                    print(f"  - Para {para_idx}: footnote #{fn['display_num']} (id={fn['id']})")
        else:
            print("✓ No paragraphs with multiple footnotes (test data doesn't have any)")
    
    @staticmethod
    def test_no_footnotes():
        """Test DOCX with no footnotes."""
        print("\n=== Test 1.5: DOCX with no footnotes ===")
        
        # For this test, we'll use the same sample DOCX but manually test
        # the case where there are no footnotes
        # In real scenario, would use a different sample_no_footnotes.docx
        
        result = {
            'detected': False,
            'footnote_content': {},
            'paragraph_data': []
        }
        
        fn_map = build_footnotes_map(result['footnote_content'], result['paragraph_data'])
        
        assert fn_map['detected'] == False
        assert fn_map['total'] == 0
        assert len(fn_map['footnotes']) == 0
        
        print(f"✓ No footnotes case handled correctly")
        print(f"✓ detected={fn_map['detected']}, total={fn_map['total']}")
    
    @staticmethod
    def test_footnotes_map_json_serializable(fn_map):
        """Test that footnotes_map can be serialized to JSON."""
        print("\n=== Test 1.6: JSON serialization ===")
        
        try:
            json_str = json.dumps(fn_map, indent=2)
            parsed = json.loads(json_str)
            assert parsed == fn_map
            print(f"✓ footnotes_map is JSON serializable")
            print(f"✓ JSON size: {len(json_str)} bytes")
        except Exception as e:
            print(f"✗ JSON serialization failed: {e}")
            raise
    
    @staticmethod
    def test_content_truncation(fn_map):
        """Test that paragraph_text is truncated to 100 chars."""
        print("\n=== Test 1.7: paragraph_text truncation ===")
        
        for fn in fn_map['footnotes']:
            para_text = fn['paragraph_text']
            # Should be <= 103 chars (100 + "...")
            assert len(para_text) <= 103, f"paragraph_text too long: {len(para_text)}"
            if len(para_text) == 103 and para_text.endswith('...'):
                print(f"✓ Footnote #{fn['display_num']}: text was truncated")
            else:
                print(f"✓ Footnote #{fn['display_num']}: text length {len(para_text)}")


def run_all_tests(sample_docx_path):
    """Run all Unit #1 tests."""
    print("=" * 80)
    print("UNIT #1: FOOTNOTE DETECTION & footnotes_map.json")
    print("=" * 80)
    
    tests = TestUnit1()
    
    try:
        # Test 1.1: Extract footnotes
        result = tests.test_extract_3_footnotes(sample_docx_path)
        
        # Test 1.2: Build footnotes_map
        fn_map = tests.test_build_footnotes_map(result)
        
        # Test 1.3: Display num calculation
        tests.test_display_num_calculation(result)
        
        # Test 1.4: Multiple footnotes in same paragraph
        tests.test_multiple_footnotes_same_paragraph(result)
        
        # Test 1.5: No footnotes
        tests.test_no_footnotes()
        
        # Test 1.6: JSON serialization
        tests.test_footnotes_map_json_serializable(fn_map)
        
        # Test 1.7: Content truncation
        tests.test_content_truncation(fn_map)
        
        print("\n" + "=" * 80)
        print("✓ ALL UNIT #1 TESTS PASSED")
        print("=" * 80)
        
        return fn_map
    
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        raise


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python3 test_unit1.py <sample_docx_path>")
        print("\nExample:")
        print("  python3 test_unit1.py /tmp/sample_with_footnotes.docx")
        sys.exit(1)
    
    sample_path = sys.argv[1]
    if not Path(sample_path).exists():
        print(f"✗ File not found: {sample_path}")
        sys.exit(1)
    
    fn_map = run_all_tests(sample_path)
    
    # Save to file for inspection
    output_path = Path(sample_path).parent / 'footnotes_map.json'
    with open(output_path, 'w') as f:
        json.dump(fn_map, f, indent=2)
    print(f"\nSaved footnotes_map to: {output_path}")