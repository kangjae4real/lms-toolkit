"""main.py CLI 인자 파싱 테스트"""

from src.auto_watch.main import _parse_args


def test_no_transcribe_flag(monkeypatch):
    monkeypatch.setattr("sys.argv", ["lms-toolkit", "--no-transcribe"])
    args = _parse_args()
    assert args.transcribe is False


def test_transcribe_flag(monkeypatch):
    monkeypatch.setattr("sys.argv", ["lms-toolkit", "--transcribe"])
    args = _parse_args()
    assert args.transcribe is True
