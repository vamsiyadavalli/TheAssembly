"""Tests for Gemini image generation wiring in theassembly.workout_image."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_workout():
    from theassembly.models import WorkoutRecord
    return WorkoutRecord.from_dict(
        {
            "date": "2026-04-28",
            "release_time": "20:00",
            "content": "5 Rounds for Time",
            "stimulus": "Aerobic Endurance",
            "technical_cues": ["Keep a steady pace."],
            "movements": [{"name": "Burpees", "reps": "10"}],
        }
    )


def _make_valid_png_bytes(width: int = 1024, height: int = 576) -> bytes:
    from io import BytesIO
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (width, height), color=(12, 24, 48)).save(buffer, format="PNG")
    return buffer.getvalue()


def _fake_genai_module(image_data: bytes | None):
    """Build a minimal fake `google.genai` module tree for mocking."""
    # Build fake inline_data / part
    fake_part = MagicMock()
    if image_data is not None:
        fake_inline = MagicMock()
        fake_inline.data = image_data
        fake_part.inline_data = fake_inline
    else:
        fake_part.inline_data = None

    # Build fake response
    fake_content = MagicMock()
    fake_content.parts = [fake_part]
    fake_candidate = MagicMock()
    fake_candidate.content = fake_content
    fake_response = MagicMock()
    fake_response.candidates = [fake_candidate]

    # Build fake client
    fake_models = MagicMock()
    fake_models.generate_content.return_value = fake_response
    fake_client_instance = MagicMock()
    fake_client_instance.models = fake_models

    # Build fake google.genai module — must be a MagicMock so attribute access works
    fake_genai = MagicMock()
    fake_genai.Client.return_value = fake_client_instance

    # Build fake google.genai.types — MagicMock so GenerateContentConfig/ImageConfig work
    fake_types = MagicMock()
    fake_genai.types = fake_types

    # Build fake google package so `from google import genai` works
    fake_google = MagicMock()
    fake_google.genai = fake_genai

    return {
        "google": fake_google,
        "google.genai": fake_genai,
        "google.genai.types": fake_types,
        "_client_instance": fake_client_instance,
        "_fake_genai": fake_genai,
        "_fake_types": fake_types,
    }


# ---------------------------------------------------------------------------
# generate_gemini_image — happy path
# ---------------------------------------------------------------------------

class GenerateGeminiImageTests(unittest.TestCase):
    def test_writes_png_on_success(self, tmp_path: Path | None = None) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.png"
            fake_image_bytes = _make_valid_png_bytes()

            modules = _fake_genai_module(fake_image_bytes)
            with patch.dict(sys.modules, modules):
                # Force re-import of workout_image so it uses the patched module
                if "theassembly.workout_image" in sys.modules:
                    del sys.modules["theassembly.workout_image"]
                from theassembly.workout_image import generate_gemini_image

                generate_gemini_image(
                    prompt="test prompt",
                    output_path=output_path,
                    api_key="test-api-key",
                    model="gemini-2.5-flash-image",
                    aspect_ratio="16:9",
                )

            self.assertTrue(output_path.exists())
            self.assertEqual(output_path.read_bytes(), fake_image_bytes)

    def test_creates_parent_dirs(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "deep" / "output.png"
            fake_image_bytes = _make_valid_png_bytes()

            modules = _fake_genai_module(fake_image_bytes)
            with patch.dict(sys.modules, modules):
                if "theassembly.workout_image" in sys.modules:
                    del sys.modules["theassembly.workout_image"]
                from theassembly.workout_image import generate_gemini_image

                generate_gemini_image(
                    prompt="test prompt",
                    output_path=output_path,
                    api_key="test-key",
                )

            self.assertTrue(output_path.exists())

    def test_raises_gemini_image_error_when_no_image_part(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.png"

            modules = _fake_genai_module(image_data=None)
            with patch.dict(sys.modules, modules):
                if "theassembly.workout_image" in sys.modules:
                    del sys.modules["theassembly.workout_image"]
                from theassembly.workout_image import GeminiImageError, generate_gemini_image

                with self.assertRaises(GeminiImageError):
                    generate_gemini_image(
                        prompt="test prompt",
                        output_path=output_path,
                        api_key="test-key",
                    )
            self.assertFalse(output_path.exists())

    def test_raises_when_response_has_no_candidates(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.png"

            modules = _fake_genai_module(_make_valid_png_bytes())
            modules["_client_instance"].models.generate_content.return_value.candidates = []

            with patch.dict(sys.modules, modules):
                if "theassembly.workout_image" in sys.modules:
                    del sys.modules["theassembly.workout_image"]
                from theassembly.workout_image import GeminiImageError, generate_gemini_image

                with self.assertRaises(GeminiImageError):
                    generate_gemini_image(
                        prompt="test prompt",
                        output_path=output_path,
                        api_key="test-key",
                    )

    def test_honors_retry_delay_with_cap(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.png"
            modules = _fake_genai_module(_make_valid_png_bytes())

            fake_error = Exception("429 rate limit retryDelay: '30s'")
            fake_response = modules["_client_instance"].models.generate_content.return_value
            modules["_client_instance"].models.generate_content.side_effect = [fake_error, fake_response]

            with patch.dict(sys.modules, modules):
                if "theassembly.workout_image" in sys.modules:
                    del sys.modules["theassembly.workout_image"]
                from theassembly.workout_image import generate_gemini_image

                with patch("theassembly.workout_image.random.uniform", return_value=1.0):
                    with patch("theassembly.workout_image.time.sleep") as mock_sleep:
                        generate_gemini_image(
                            prompt="test prompt",
                            output_path=output_path,
                            api_key="test-key",
                            max_retries=2,
                            max_retry_delay_seconds=5.0,
                            retry_jitter_ratio=0.1,
                        )

            mock_sleep.assert_called_once_with(5.0)

    def test_quota_with_retry_hint_retries(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.png"
            modules = _fake_genai_module(_make_valid_png_bytes())

            fake_error = Exception("429 RESOURCE_EXHAUSTED retryDelay: '2s'")
            fake_response = modules["_client_instance"].models.generate_content.return_value
            modules["_client_instance"].models.generate_content.side_effect = [fake_error, fake_response]

            with patch.dict(sys.modules, modules):
                if "theassembly.workout_image" in sys.modules:
                    del sys.modules["theassembly.workout_image"]
                from theassembly.workout_image import generate_gemini_image

                with patch("theassembly.workout_image.random.uniform", return_value=1.0):
                    with patch("theassembly.workout_image.time.sleep") as mock_sleep:
                        generate_gemini_image(
                            prompt="test prompt",
                            output_path=output_path,
                            api_key="test-key",
                            max_retries=2,
                            max_retry_delay_seconds=10.0,
                            retry_jitter_ratio=0.1,
                        )

            mock_sleep.assert_called_once_with(2.0)

    def test_quota_without_retry_hint_fails_fast(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.png"
            modules = _fake_genai_module(_make_valid_png_bytes())
            modules["_client_instance"].models.generate_content.side_effect = Exception("RESOURCE_EXHAUSTED")

            with patch.dict(sys.modules, modules):
                if "theassembly.workout_image" in sys.modules:
                    del sys.modules["theassembly.workout_image"]
                from theassembly.workout_image import GeminiAPIError, generate_gemini_image

                with patch("theassembly.workout_image.time.sleep") as mock_sleep:
                    with self.assertRaises(GeminiAPIError):
                        generate_gemini_image(
                            prompt="test prompt",
                            output_path=output_path,
                            api_key="test-key",
                            max_retries=2,
                        )
            mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# CLI _run_gemini_mode — missing API key
# ---------------------------------------------------------------------------

class RunGeminiModeTests(unittest.TestCase):
    def test_raises_runtime_error_when_no_api_key(self) -> None:
        import os, tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "2026-04-28.png"
            workout = _make_workout()

            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("GEMINI_API_KEY", None)
                os.environ.pop("GOOGLE_API_KEY", None)

                # Import fresh (no google-genai needed for this path)
                if "tools.generate_workout_image" in sys.modules:
                    del sys.modules["tools.generate_workout_image"]

                import importlib, importlib.util
                spec = importlib.util.spec_from_file_location(
                    "generate_workout_image",
                    Path(__file__).parent.parent / "tools" / "generate_workout_image.py",
                )
                mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
                spec.loader.exec_module(mod)  # type: ignore[union-attr]

                with patch.object(mod, "_REPO_ROOT", Path(tmpdir)):
                    with self.assertRaises(RuntimeError) as ctx:
                        mod._run_gemini_mode(workout, output_path)

                self.assertIn("GEMINI_API_KEY", str(ctx.exception))

    def test_uses_streamlit_secrets_when_env_missing(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "2026-04-28.png"
            workout = _make_workout()

            if "tools.generate_workout_image" in sys.modules:
                del sys.modules["tools.generate_workout_image"]

            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "generate_workout_image",
                Path(__file__).parent.parent / "tools" / "generate_workout_image.py",
            )
            mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(mod)  # type: ignore[union-attr]

            repo_root = Path(tmpdir) / "fake_repo"
            secrets_dir = repo_root / ".streamlit"
            secrets_dir.mkdir(parents=True, exist_ok=True)
            (secrets_dir / "secrets.toml").write_text(
                'GEMINI_API_KEY = "AIzaSySECRETKEYEXAMPLE1234567890"\n',
                encoding="utf-8",
            )

            with patch.dict("os.environ", {}, clear=False):
                import os
                os.environ.pop("GEMINI_API_KEY", None)
                os.environ.pop("GOOGLE_API_KEY", None)

                with patch.object(mod, "_REPO_ROOT", repo_root):
                    with patch("theassembly.workout_image.generate_gemini_image") as mock_generate:
                        mock_generate.return_value = None
                        mod._run_gemini_mode(workout, output_path)

                        called = mock_generate.call_args.kwargs
                        self.assertEqual(called["api_key"], "AIzaSySECRETKEYEXAMPLE1234567890")

    def test_env_key_takes_precedence_over_streamlit_secrets(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "2026-04-28.png"
            workout = _make_workout()

            if "tools.generate_workout_image" in sys.modules:
                del sys.modules["tools.generate_workout_image"]

            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "generate_workout_image",
                Path(__file__).parent.parent / "tools" / "generate_workout_image.py",
            )
            mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(mod)  # type: ignore[union-attr]

            repo_root = Path(tmpdir) / "fake_repo"
            secrets_dir = repo_root / ".streamlit"
            secrets_dir.mkdir(parents=True, exist_ok=True)
            (secrets_dir / "secrets.toml").write_text(
                'GEMINI_API_KEY = "AIzaSySECRETKEYEXAMPLE1234567890"\n',
                encoding="utf-8",
            )

            with patch.dict("os.environ", {"GEMINI_API_KEY": "AIzaSyENVKEYEXAMPLE1234567890"}, clear=False):
                with patch.object(mod, "_REPO_ROOT", repo_root):
                    with patch("theassembly.workout_image.generate_gemini_image") as mock_generate:
                        mock_generate.return_value = None
                        mod._run_gemini_mode(workout, output_path)

                        called = mock_generate.call_args.kwargs
                        self.assertEqual(called["api_key"], "AIzaSyENVKEYEXAMPLE1234567890")

    def test_raises_runtime_error_when_no_key_in_env_or_secrets(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "2026-04-28.png"
            workout = _make_workout()

            if "tools.generate_workout_image" in sys.modules:
                del sys.modules["tools.generate_workout_image"]

            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "generate_workout_image",
                Path(__file__).parent.parent / "tools" / "generate_workout_image.py",
            )
            mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(mod)  # type: ignore[union-attr]

            repo_root = Path(tmpdir) / "fake_repo"
            (repo_root / ".streamlit").mkdir(parents=True, exist_ok=True)

            with patch.dict("os.environ", {}, clear=False):
                import os
                os.environ.pop("GEMINI_API_KEY", None)
                os.environ.pop("GOOGLE_API_KEY", None)

                with patch.object(mod, "_REPO_ROOT", repo_root):
                    with self.assertRaises(RuntimeError) as ctx:
                        mod._run_gemini_mode(workout, output_path)

                self.assertIn("GEMINI_API_KEY", str(ctx.exception))

    def test_raises_runtime_error_on_api_failure(self) -> None:
        import os, tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "2026-04-28.png"
            workout = _make_workout()

            modules = _fake_genai_module(image_data=None)  # no image = GeminiImageError path
            with patch.dict(sys.modules, modules):
                with patch.dict(os.environ, {"GEMINI_API_KEY": "AIzaSyFAKEKEYEXAMPLE1234567890"}):
                    if "theassembly.workout_image" in sys.modules:
                        del sys.modules["theassembly.workout_image"]

                    import importlib.util
                    spec = importlib.util.spec_from_file_location(
                        "generate_workout_image",
                        Path(__file__).parent.parent / "tools" / "generate_workout_image.py",
                    )
                    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
                    spec.loader.exec_module(mod)  # type: ignore[union-attr]

                    with self.assertRaises(RuntimeError):
                        mod._run_gemini_mode(workout, output_path)

    def test_quota_error_is_classified_in_runtime_message(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "2026-04-28.png"
            workout = _make_workout()

            if "tools.generate_workout_image" in sys.modules:
                del sys.modules["tools.generate_workout_image"]

            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "generate_workout_image",
                Path(__file__).parent.parent / "tools" / "generate_workout_image.py",
            )
            mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(mod)  # type: ignore[union-attr]

            with patch("theassembly.workout_image.generate_gemini_image") as mock_generate:
                from theassembly.workout_image import GeminiAPIError, GeminiErrorInfo

                mock_generate.side_effect = GeminiAPIError(
                    GeminiErrorInfo(
                        category="quota_exhausted",
                        retry_after_seconds=6.0,
                        message="429 RESOURCE_EXHAUSTED",
                    )
                )
                with patch.dict("os.environ", {"GEMINI_API_KEY": "AIzaSyFAKEKEYEXAMPLE1234567890"}):
                    with self.assertRaises(RuntimeError) as ctx:
                        mod._run_gemini_mode(workout, output_path)

                self.assertIn("[quota_exhausted]", str(ctx.exception))

    def test_preflight_fails_when_required_sections_missing(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "2026-04-28.png"
            workout = _make_workout()

            if "tools.generate_workout_image" in sys.modules:
                del sys.modules["tools.generate_workout_image"]

            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "generate_workout_image",
                Path(__file__).parent.parent / "tools" / "generate_workout_image.py",
            )
            mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(mod)  # type: ignore[union-attr]

            with patch("theassembly.workout_image.build_image_prompt", return_value="missing sections"):
                with patch("theassembly.workout_image.generate_gemini_image") as mock_generate:
                    with patch.dict("os.environ", {"GEMINI_API_KEY": "AIzaSyDUMMY_VALID_LENGTH_KEY"}):
                        with self.assertRaises(RuntimeError) as ctx:
                            mod._run_gemini_mode(workout, output_path)

            self.assertIn("[quality_failed]", str(ctx.exception))
            mock_generate.assert_not_called()

    def test_preflight_fails_when_prompt_too_long(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "2026-04-28.png"
            workout = _make_workout()

            if "tools.generate_workout_image" in sys.modules:
                del sys.modules["tools.generate_workout_image"]

            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "generate_workout_image",
                Path(__file__).parent.parent / "tools" / "generate_workout_image.py",
            )
            mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(mod)  # type: ignore[union-attr]

            huge_prompt = (
                "Semantic Source Of Truth\nWOD_COUNT: 1\nWOD_ROWS:\n1|10|Burpees\n"
                "Header (large, bold):\nWorkout Sections (left/middle panels with images):\nDesign Style:\n"
                + ("x" * 500)
            )

            with patch("theassembly.workout_image.build_image_prompt", return_value=huge_prompt):
                with patch("theassembly.workout_image.generate_gemini_image") as mock_generate:
                    with patch.dict(
                        "os.environ",
                        {
                            "GEMINI_API_KEY": "AIzaSyDUMMY_VALID_LENGTH_KEY",
                            "GEMINI_MAX_PROMPT_CHARS": "200",
                        },
                    ):
                        with self.assertRaises(RuntimeError) as ctx:
                            mod._run_gemini_mode(workout, output_path)

            self.assertIn("[quality_failed]", str(ctx.exception))
            self.assertIn("Prompt too long", str(ctx.exception))
            mock_generate.assert_not_called()

    def test_process_date_uses_prompt_fallback_on_quota_error(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            if "tools.generate_workout_image" in sys.modules:
                del sys.modules["tools.generate_workout_image"]

            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "generate_workout_image",
                Path(__file__).parent.parent / "tools" / "generate_workout_image.py",
            )
            mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(mod)  # type: ignore[union-attr]

            workout = _make_workout()
            args = type(
                "Args",
                (),
                {
                    "output_dir": tmpdir,
                    "mode": "gemini",
                    "fallback": "prompt",
                    "overwrite": False,
                },
            )()

            with patch.object(mod, "_run_gemini_mode", side_effect=RuntimeError("[quota_exhausted] 429")):
                code, outcome = mod._process_date(workout.workout_date, args, [workout])

            self.assertEqual(code, 0)
            self.assertEqual(outcome, "fallback-prompt-quota_exhausted")
            self.assertTrue((Path(tmpdir) / f"{workout.workout_date.isoformat()}.txt").exists())

            meta = json.loads((Path(tmpdir) / f"{workout.workout_date.isoformat()}.meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["status"], "success")
            self.assertEqual(meta["outcome"], "fallback-prompt-quota_exhausted")
            self.assertEqual(meta["effective_mode"], "prompt")
            self.assertTrue(meta["prompt_sha256"])

    def test_process_date_uses_prompt_fallback_on_quality_error(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            if "tools.generate_workout_image" in sys.modules:
                del sys.modules["tools.generate_workout_image"]

            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "generate_workout_image",
                Path(__file__).parent.parent / "tools" / "generate_workout_image.py",
            )
            mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(mod)  # type: ignore[union-attr]

            workout = _make_workout()
            args = type(
                "Args",
                (),
                {
                    "output_dir": tmpdir,
                    "mode": "gemini",
                    "fallback": "prompt",
                    "overwrite": False,
                },
            )()

            with patch.object(mod, "_run_gemini_mode", side_effect=RuntimeError("[quality_failed] aspect mismatch")):
                code, outcome = mod._process_date(workout.workout_date, args, [workout])

            self.assertEqual(code, 0)
            self.assertEqual(outcome, "fallback-prompt-quality_failed")

            meta = json.loads((Path(tmpdir) / f"{workout.workout_date.isoformat()}.meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["status"], "success")
            self.assertEqual(meta["outcome"], "fallback-prompt-quality_failed")
            self.assertEqual(meta["effective_mode"], "prompt")
            self.assertEqual(meta["validation_passed"], False)
            self.assertIn("quality_failed", meta["validation_error"])

    def test_process_date_gemini_success_writes_prompt_artifact(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            if "tools.generate_workout_image" in sys.modules:
                del sys.modules["tools.generate_workout_image"]

            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "generate_workout_image",
                Path(__file__).parent.parent / "tools" / "generate_workout_image.py",
            )
            mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(mod)  # type: ignore[union-attr]

            workout = _make_workout()
            args = type(
                "Args",
                (),
                {
                    "output_dir": tmpdir,
                    "mode": "gemini",
                    "fallback": "prompt",
                    "overwrite": False,
                },
            )()

            prompt_text = "Semantic Source Of Truth\nWOD_COUNT: 1\nWOD_ROWS:\n1|10|Burpees"
            with patch.object(
                mod,
                "_run_gemini_mode",
                return_value=(
                    prompt_text,
                    "gemini-2.5-flash-image",
                    "16:9",
                    {
                        "image_bytes": 3,
                        "image_width": 1,
                        "image_height": 1,
                        "langgraph_enabled": 0,
                    },
                ),
            ):
                code, outcome = mod._process_date(workout.workout_date, args, [workout])

            self.assertEqual(code, 0)
            self.assertEqual(outcome, "gemini")

            prompt_path = Path(tmpdir) / f"{workout.workout_date.isoformat()}.txt"
            self.assertTrue(prompt_path.exists())
            self.assertEqual(prompt_path.read_text(encoding="utf-8"), prompt_text)

            meta = json.loads((Path(tmpdir) / f"{workout.workout_date.isoformat()}.meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["status"], "success")
            self.assertEqual(meta["effective_mode"], "gemini")
            self.assertEqual(meta["prompt_path"], str(prompt_path))
            self.assertEqual(meta["prompt_length"], len(prompt_text))
            self.assertTrue(meta["prompt_sha256"])

    def test_process_date_writes_skipped_metadata_when_output_exists(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            if "tools.generate_workout_image" in sys.modules:
                del sys.modules["tools.generate_workout_image"]

            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "generate_workout_image",
                Path(__file__).parent.parent / "tools" / "generate_workout_image.py",
            )
            mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(mod)  # type: ignore[union-attr]

            workout = _make_workout()
            out = Path(tmpdir) / f"{workout.workout_date.isoformat()}.png"
            out.write_bytes(b"existing")
            args = type(
                "Args",
                (),
                {
                    "output_dir": tmpdir,
                    "mode": "poster",
                    "fallback": "prompt",
                    "overwrite": False,
                },
            )()

            code, outcome = mod._process_date(workout.workout_date, args, [workout])
            self.assertEqual(code, 0)
            self.assertEqual(outcome, "skipped")

            meta = json.loads((Path(tmpdir) / f"{workout.workout_date.isoformat()}.meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["status"], "skipped")
            self.assertEqual(meta["effective_mode"], "skipped")

    def test_process_date_overwrites_existing_when_flag_set(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            if "tools.generate_workout_image" in sys.modules:
                del sys.modules["tools.generate_workout_image"]

            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "generate_workout_image",
                Path(__file__).parent.parent / "tools" / "generate_workout_image.py",
            )
            mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(mod)  # type: ignore[union-attr]

            workout = _make_workout()
            out = Path(tmpdir) / f"{workout.workout_date.isoformat()}.png"
            out.write_bytes(b"existing")
            args = type(
                "Args",
                (),
                {
                    "output_dir": tmpdir,
                    "mode": "poster",
                    "fallback": "prompt",
                    "overwrite": True,
                },
            )()

            with patch.object(mod, "_run_poster_mode", side_effect=lambda _w, p: p.write_bytes(b"new")):
                code, outcome = mod._process_date(workout.workout_date, args, [workout])

            self.assertEqual(code, 0)
            self.assertEqual(outcome, "poster")
            self.assertEqual(out.read_bytes(), b"new")


# ---------------------------------------------------------------------------
# Prompt builder still works end-to-end (smoke test with real workout)
# ---------------------------------------------------------------------------

class PromptBuilderRegressionTest(unittest.TestCase):
    def test_prompt_contains_required_sections(self) -> None:
        # Ensure the prompt builder is unaffected by Gemini additions
        if "theassembly.workout_image" in sys.modules:
            del sys.modules["theassembly.workout_image"]
        from theassembly.workout_image import build_image_prompt

        workout = _make_workout()
        prompt = build_image_prompt(workout)

        self.assertIn("high-contrast", prompt)
        self.assertIn("5 ROUNDS FOR TIME", prompt)
        self.assertIn("Design Style:", prompt)


if __name__ == "__main__":
    unittest.main()
