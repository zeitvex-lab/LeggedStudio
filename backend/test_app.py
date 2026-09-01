import unittest
import sys

from app import api_response, filter_records


class ApiResponseTests(unittest.TestCase):
    def test_health(self):
        status, payload = api_response("/api/health", {})
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["python_target"], "3.12")
        self.assertEqual(payload["python_target_match"], sys.version_info[:2] == (3, 12))

    def test_filters_and_family(self):
        status, payload = api_response("/api/assets", {"size": ["M"], "locomotion": ["point_foot"]})
        self.assertEqual(status, 200)
        self.assertTrue(payload["records"])
        self.assertTrue(all(r.get("size_class_by_mass") == "M" for r in payload["records"]))

        status, payload = api_response("/api/assets/unitree_go2", {})
        self.assertEqual(status, 200)
        self.assertEqual(payload["family"], "unitree_go2")

    def test_summary_exposes_inventory_metadata(self):
        status, payload = api_response("/api/summary", {})
        self.assertEqual(status, 200)
        self.assertEqual(payload["schema_version"], "quadruped-asset-inventory-1.1")
        self.assertEqual(payload["document_role"], "machine_fact_source")
        self.assertEqual(payload["size_taxonomy"]["M"], "15 <= mass_kg < 35")

    def test_unknown_family_is_json_404(self):
        status, payload = api_response("/api/assets/no_such_family", {})
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "family_not_found")

    def test_known_family_with_empty_filter_is_success(self):
        status, payload = api_response(
            "/api/assets/unitree_go2", {"locomotion": ["wheel_leg"]}
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 0)


if __name__ == "__main__":
    unittest.main()
