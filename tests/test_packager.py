import zipfile
from pathlib import Path

from agentcore_push.packager import build_deployment_package


def test_build_package_includes_entrypoint_without_dependencies(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    agent_file = tmp_path / "hello.py"
    agent_file.write_text("print('hello')\n")

    package = build_deployment_package(
        agent_file,
        install_dependencies=False,
        keep_build=True,
    )

    assert package.entry_point == "hello.py"
    assert package.zip_path.exists()

    with zipfile.ZipFile(package.zip_path) as archive:
        assert "hello.py" in archive.namelist()
        info = archive.getinfo("hello.py")
        assert (info.external_attr >> 16) == 0o644
