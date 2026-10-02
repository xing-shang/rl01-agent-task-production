import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from check_rl01_archive import check_archive
from check_rl01_package import validate
from test_check_rl01_package import write_package_fixture


class FinalArchivePreflightTests(unittest.TestCase):
    def create_archive(self, temporary):
        batch = Path(temporary) / "batch"
        task = batch / "FIN-QA-001"
        task.mkdir(parents=True)
        write_package_fixture(task)
        (batch / "交付文档.md").write_text("Local test fixture only.\n")
        archive = Path(temporary) / "final.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
            for path in sorted(batch.rglob("*")):
                if path.is_file():
                    output.write(path, path.relative_to(batch.parent).as_posix())
        return task, archive

    def test_valid_zip_preserves_modes_and_binds_actual_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, archive = self.create_archive(temporary)
            result = check_archive(archive)
            self.assertTrue(result["ok"], result)
            self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), result["archive_sha256"])
            self.assertTrue(result["checker_sha256"] and result["task_checker_sha256"])

    def test_residue_added_after_task_preflight_blocks_final_zip(self):
        with tempfile.TemporaryDirectory() as temporary:
            task, archive = self.create_archive(temporary)
            self.assertFalse(validate(task)[0])
            first_hash = check_archive(archive)["archive_sha256"]
            with zipfile.ZipFile(archive, "a") as output:
                output.writestr("batch/.DS_Store", b"Finder metadata")
                output.writestr("__MACOSX/batch/._README.md", b"resource fork")
            result = check_archive(archive)
            self.assertFalse(result["ok"])
            self.assertTrue(result["tasks"][0]["ok"])
            self.assertEqual({"archive-residue"}, {issue["rule"] for issue in result["issues"]})
            self.assertNotEqual(first_hash, result["archive_sha256"])

    def test_actual_zip_task_failure_is_not_overridden_by_old_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, archive = self.create_archive(temporary)
            with zipfile.ZipFile(archive, "a") as output:
                output.writestr("batch/evidence/preflight.json", '{"ok": true}')
                output.writestr("batch/FIN-QA-001/.DS_Store", b"residue")
            result = check_archive(archive)
            self.assertFalse(result["ok"])
            self.assertFalse(result["tasks"][0]["ok"])

    def test_traversal_is_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, archive = self.create_archive(temporary)
            with zipfile.ZipFile(archive, "a") as output:
                output.writestr("../escaped.txt", b"invalid")
            result = check_archive(archive)
            self.assertFalse(result["ok"])
            self.assertEqual({"archive-path"}, {issue["rule"] for issue in result["issues"]})
            self.assertFalse((Path(temporary).parent / "escaped.txt").exists())


if __name__ == "__main__":
    unittest.main()
