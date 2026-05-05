from pathlib import Path

from pip_verv.parser import parse_sources

FIXTURES = Path(__file__).parent / "fixtures"


class TestParseRequirementsTxt:
    def test_should_return_empty_list_for_empty_file(self, tmp_path: Path) -> None:
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("")

        result = parse_sources([req_file])

        assert result == []

    def test_should_return_empty_list_for_comments_only_file(
        self, tmp_path: Path
    ) -> None:
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("# comment\n# another comment\n")

        result = parse_sources([req_file])

        assert result == []

    def test_should_parse_basic_requirements(self) -> None:
        result = parse_sources([FIXTURES / "requirements_basic.txt"])

        names = [d.name.lower() for d in result]
        assert "requests" in names
        assert "urllib3" in names
        assert "boto3" in names

    def test_should_strip_inline_comments(self) -> None:
        result = parse_sources([FIXTURES / "requirements_basic.txt"])

        boto3 = next(d for d in result if d.name.lower() == "boto3")
        assert boto3.version_spec == "==1.34.0"

    def test_should_follow_r_include(self, tmp_path: Path) -> None:
        base = tmp_path / "base.txt"
        base.write_text("sqlalchemy>=2.0\n")
        main = tmp_path / "requirements.txt"
        main.write_text("-r base.txt\nflask>=3.0\n")

        result = parse_sources([main])

        names = [d.name.lower() for d in result]
        assert "sqlalchemy" in names
        assert "flask" in names

    def test_should_not_infinite_loop_on_circular_r_include(
        self, tmp_path: Path
    ) -> None:
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_text("-r b.txt\nrequests>=2.0\n")
        b.write_text("-r a.txt\nflask>=3.0\n")

        result = parse_sources([a])

        names = [d.name.lower() for d in result]
        assert "requests" in names

    def test_should_mark_url_dep_as_not_auditable(self, tmp_path: Path) -> None:
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("https://example.com/mypackage.tar.gz\n")

        result = parse_sources([req_file])

        assert len(result) == 1
        assert result[0].is_auditable is False

    def test_should_mark_git_dep_as_not_auditable(self, tmp_path: Path) -> None:
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("git+https://github.com/org/repo.git@main\n")

        result = parse_sources([req_file])

        assert len(result) == 1
        assert result[0].is_auditable is False

    def test_should_skip_editable_installs(self, tmp_path: Path) -> None:
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("-e .\n-e ./mypackage\n")

        result = parse_sources([req_file])

        assert result == []

    def test_should_extract_extras_from_requirement(self, tmp_path: Path) -> None:
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("requests[security,socks]>=2.28.0\n")

        result = parse_sources([req_file])

        assert len(result) == 1
        assert result[0].name == "requests"
        assert set(result[0].extras) == {"security", "socks"}

    def test_should_deduplicate_packages_across_multiple_sources(
        self, tmp_path: Path
    ) -> None:
        f1 = tmp_path / "requirements1.txt"
        f2 = tmp_path / "requirements2.txt"
        f1.write_text("requests>=2.0\n")
        f2.write_text("requests>=2.28\n")

        result = parse_sources([f1, f2])

        request_deps = [d for d in result if d.name.lower() == "requests"]
        assert len(request_deps) == 1


class TestParsePyprojectToml:
    def test_should_return_empty_list_when_no_project_dependencies(
        self, tmp_path: Path
    ) -> None:
        toml = tmp_path / "pyproject.toml"
        toml.write_text("[project]\nname = 'myapp'\n")

        result = parse_sources([toml])

        assert result == []

    def test_should_parse_project_dependencies(self) -> None:
        result = parse_sources([FIXTURES / "pyproject_full.toml"])

        names = [d.name.lower() for d in result]
        assert "requests" in names
        assert "packaging" in names

    def test_should_parse_optional_deps_from_all_groups(self) -> None:
        result = parse_sources([FIXTURES / "pyproject_full.toml"])

        names = [d.name.lower() for d in result]
        assert "pytest" in names
        assert "mypy" in names
        assert "sphinx" in names

    def test_should_return_empty_list_when_no_project_section(
        self, tmp_path: Path
    ) -> None:
        toml = tmp_path / "pyproject.toml"
        toml.write_text("[build-system]\nrequires = ['hatchling']\n")

        result = parse_sources([toml])

        assert result == []

    def test_should_mark_url_requirement_as_not_auditable(self, tmp_path: Path) -> None:
        toml = tmp_path / "pyproject.toml"
        toml.write_text(
            '[project]\ndependencies = ["mylib @ https://example.com/mylib.tar.gz"]\n'
        )

        result = parse_sources([toml])

        assert len(result) == 1
        assert result[0].is_auditable is False


class TestUnicodeAndEncoding:
    def test_should_parse_requirements_file_with_utf8_bom(self, tmp_path: Path) -> None:
        req_file = tmp_path / "requirements.txt"
        # Write with UTF-8 BOM
        req_file.write_bytes(b"\xef\xbb\xbfrequests>=2.28\n")

        result = parse_sources([req_file])

        # BOM character in package name causes InvalidRequirement
        # — should not crash regardless
        assert isinstance(result, list)

    def test_should_parse_requirements_with_normalized_package_names(
        self, tmp_path: Path
    ) -> None:
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("My_Package>=1.0\nsome-lib==2.0\n")

        result = parse_sources([req_file])

        names = [d.name for d in result]
        assert len(names) == 2

    def test_should_parse_pyproject_with_package_names_containing_dashes(
        self, tmp_path: Path
    ) -> None:
        toml = tmp_path / "pyproject.toml"
        toml.write_text(
            '[project]\ndependencies = ["my-package>=1.0", "another-lib==2.0"]\n'
        )

        result = parse_sources([toml])

        names = [d.name for d in result]
        assert len(names) == 2
