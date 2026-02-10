#!/usr/bin/env python3
"""Test script for Case Browser functionality (FBI and NamUs APIs)."""

import sys
sys.path.insert(0, 'src')

import requests
from deeptrace.namus_client import NamUsClient

def test_fbi_api():
    """Test FBI Most Wanted API."""
    print("=" * 60)
    print("Testing FBI Most Wanted API")
    print("=" * 60)

    try:
        response = requests.get("https://api.fbi.gov/@wanted", timeout=10)
        response.raise_for_status()
        data = response.json()

        total_items = len(data.get("items", []))
        print(f"✓ FBI API working")
        print(f"  Total items available: {total_items}")

        if total_items > 0:
            first_item = data["items"][0]
            print(f"\nSample case:")
            print(f"  ID: {first_item.get('uid')}")
            print(f"  Title: {first_item.get('title', 'Unknown')}")
            print(f"  Subjects: {', '.join(first_item.get('subjects', [])[:3])}")
            print(f"  Has images: {len(first_item.get('images', [])) > 0}")

        return True

    except Exception as e:
        print(f"✗ FBI API failed: {e}")
        return False


def test_namus_client():
    """Test NamUs client functionality."""
    print("\n" + "=" * 60)
    print("Testing NamUs Client")
    print("=" * 60)

    try:
        client = NamUsClient()

        # Test 1: Get states
        print("\n1. Testing get_states()...")
        states = client.get_states()
        print(f"   ✓ Found {len(states)} states")
        print(f"   Sample: {states[0]['displayName']} ({states[0]['name']})")

        # Test 2: Search missing persons (small sample)
        print("\n2. Testing search_cases (Missing Persons, limit=5)...")
        results = client.search_cases("missing", state="California", limit=5)
        print(f"   ✓ Total cases in California: {results['count']}")
        print(f"   Returned: {len(results['results'])} cases")

        if results['results']:
            case_num = results['results'][0]['namus2Number']
            print(f"   Sample case ID: MP{case_num}")

            # Test 3: Get full case details
            print(f"\n3. Testing get_case (MP{case_num})...")
            full_case = client.get_case("missing", case_num)
            print(f"   ✓ Retrieved case: {full_case['idFormatted']}")

            # Test 4: Transform to DeepTrace format
            print(f"\n4. Testing transform_missing_person()...")
            transformed = client.transform_missing_person(full_case)
            print(f"   ✓ Transformed successfully")
            print(f"   Title: {transformed['title']}")
            print(f"   Subject: {transformed['subject_name']}")
            print(f"   Last seen: {transformed['last_seen_location']}")
            print(f"   Physical: {transformed['physical_description'][:100]}...")

        client.close()
        return True

    except Exception as e:
        print(f"✗ NamUs client failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_namus_unidentified():
    """Test NamUs unidentified persons search."""
    print("\n" + "=" * 60)
    print("Testing NamUs Unidentified Persons")
    print("=" * 60)

    try:
        client = NamUsClient()

        print("\n1. Searching unidentified persons (California, limit=3)...")
        results = client.search_cases("unidentified", state="California", limit=3)
        print(f"   ✓ Total cases in California: {results['count']}")
        print(f"   Returned: {len(results['results'])} cases")

        if results['results']:
            case_num = results['results'][0]['namus2Number']
            print(f"\n2. Getting full case details for UP{case_num}...")
            full_case = client.get_case("unidentified", case_num)
            transformed = client.transform_unidentified_person(full_case)

            print(f"   ✓ Case: {transformed['title']}")
            print(f"   Sex: {transformed['sex']}")
            print(f"   Estimated age: {transformed['estimated_age']}")
            print(f"   Found: {transformed['location_found']} on {transformed.get('date_found', 'Unknown')}")

        client.close()
        return True

    except Exception as e:
        print(f"✗ Unidentified persons test failed: {e}")
        return False


if __name__ == "__main__":
    print("DeepTrace Case Browser API Tests")
    print("=" * 60)

    results = {
        "FBI API": test_fbi_api(),
        "NamUs Client (Missing)": test_namus_client(),
        "NamUs Client (Unidentified)": test_namus_unidentified(),
    }

    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")

    all_passed = all(results.values())
    print("\n" + ("✓ All tests passed!" if all_passed else "✗ Some tests failed"))
    sys.exit(0 if all_passed else 1)
