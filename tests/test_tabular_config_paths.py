import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


SCRIPT_EXPECTATIONS = {
    "ACLED/00_add_acled_features.py": {
        "required_options": [
            "acled_raw_file",
            "acled_scaffold_file",
            "acled_output_file",
        ],
        "forbidden_literals": [
            "ACLED Data_2026-05-11_ipcch.csv",
            "ipcch_scaffold_202501_202604.csv",
            "ch_with_merged_acled_metrics.csv",
        ],
    },
    "FAO_price/00_add_fao_price_features.py": {
        "required_options": [
            "fao_raw_file_1",
            "fao_raw_file_2",
            "fao_scaffold_file",
            "fao_output_file",
            "fao_legacy_output_file",
        ],
        "forbidden_literals": [
            "FAO_DATA_FOR_MIGUEL.xlsx",
            "FOOD_CRISIS_FAO_PRICE_DATA_04012026.xlsx",
            "ipcch_scaffold_202501_202604.csv",
            "ch_with_matched_markets.csv",
            "ipcch_with_matched_markets.csv",
        ],
    },
    "WFP_indicator/00_add_wfp_price_features.py": {
        "required_options": [
            "wfp_raw_file",
            "wfp_scaffold_file",
            "wfp_esa_lookup_file",
            "wfp_output_file",
        ],
        "forbidden_literals": [
            "Prices-Export-Tue Dec 02 2025 16_03_28 GMT-0500.csv",
            "ch_scaffold.csv",
            "ch_scaffold_fixed.csv",
            "ch_WFP_prices.csv",
        ],
    },
    "WB_indicator/00_add_world_bank_features.py": {
        "required_options": [
            "wb_cpi_file",
            "wb_gdp_file",
            "wb_cc_percentile_file",
            "wb_scaffold_file",
            "wb_pip_file",
            "wb_esa_completed_file",
            "wb_country_lookup_file",
            "wb_output_file",
        ],
        "forbidden_literals": [
            "CPI.csv",
            "GDP.csv",
            "CC_percentile.csv",
            "ch_scaffold.csv",
            "pip.csv",
            "ch_ESA_completed.csv",
            "ch_scaffold_fixed.csv",
            "ch_WBG_completed.csv",
        ],
    },
}


class TabularConfigPathTests(unittest.TestCase):
    def test_tabular_scripts_use_configured_file_paths(self):
        for rel_path, expectation in SCRIPT_EXPECTATIONS.items():
            source = (ROOT / rel_path).read_text(encoding="utf-8")
            with self.subTest(script=rel_path):
                for option in expectation["required_options"]:
                    self.assertIn(option, source)
                for literal in expectation["forbidden_literals"]:
                    self.assertNotIn(literal, source)

    def test_paths_template_exposes_tabular_file_options(self):
        config_text = (ROOT / "config" / "paths_template.ini").read_text(encoding="utf-8")
        for expectation in SCRIPT_EXPECTATIONS.values():
            for option in expectation["required_options"]:
                with self.subTest(option=option):
                    self.assertIn(option + " =", config_text)


if __name__ == "__main__":
    unittest.main()
