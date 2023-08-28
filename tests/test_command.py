import json
import unittest
from argparse import Namespace
from pathlib import Path

from src.command import CycloneDXCommand


class CycloneDXConanTests(unittest.TestCase):
    def test_generation_conanfile_py(self):
        current_file = Path(__file__)
        test_input = current_file.parent / "test_files" / "conanfile.py"
        test_output = current_file.parent / "test_files" / "test_out_sbom.json"
        args = Namespace(path_or_reference=str(test_input), install_folder=None, dry_build=None,
                         output_file=str(test_output),
                         exclude_dev=False, build=None, remote=None, update=False, lockfile=None, lockfile_out=None,
                         env_host=None, env_build=None, options_host=None, options_build=None, profile_host=None,
                         profile_build=None, settings_host=None, settings_build=None, conf_host=None, conf_build=None)
        CycloneDXCommand(args).execute()
        with open(test_output) as file:
            generated_sbom_json = json.load(file)
            self.assertEqual(generated_sbom_json["bomFormat"], "CycloneDX")
            self.assertEqual(generated_sbom_json["specVersion"], "1.3")
            self.assertEqual(generated_sbom_json["version"], 1)
            self.assertEqual(generated_sbom_json["metadata"]["component"]["bom-ref"], "conan-test@1.0.0")
            self.assertEqual(generated_sbom_json["metadata"]["component"]["license"], "MIT")
            self.assertEqual(generated_sbom_json["components"][0]["license"], "MIT")
            self.assertEqual(generated_sbom_json["components"][1]["license"], "MIT")

    def test_generation_conanfile_txt(self):
        current_file = Path(__file__)
        test_input = current_file.parent / "test_files" / "conanfile.txt"
        test_output = current_file.parent / "test_files" / "test_out_from_txt_sbom.json"
        args = Namespace(path_or_reference=str(test_input), install_folder=None, dry_build=None,
                         output_file=str(test_output),
                         exclude_dev=False, build=None, remote=None, update=False, lockfile=None, lockfile_out=None,
                         env_host=None, env_build=None, options_host=None, options_build=None, profile_host=None,
                         profile_build=None, settings_host=None, settings_build=None, conf_host=None, conf_build=None)
        CycloneDXCommand(args).execute()
        with open(test_output) as file:
            generated_sbom_json = json.load(file)
            self.assertEqual(generated_sbom_json["bomFormat"], "CycloneDX")
            self.assertEqual(generated_sbom_json["specVersion"], "1.3")
            self.assertEqual(generated_sbom_json["version"], 1)
            self.assertEqual(generated_sbom_json["metadata"]["component"]["bom-ref"], "test_files@0.0.0")
            self.assertEqual(generated_sbom_json["components"][0]["license"], "MIT")


if __name__ == '__main__':
    unittest.main()
