import os
import random
import string
import requests
from src.gui.core.file_manager import get_downloads_dir


def download_video(url: str, filename: str = None) -> str:
    if filename is None:
        # 랜덤 알파벳 8자리
        filename = ''.join(random.choices(
            string.ascii_letters + string.digits, k=8))

    # 파일 확장자 추가
    if not filename.endswith('.mp4'):
        filename += '.mp4'

    try:
        save_dir = get_downloads_dir()
        filepath = os.path.join(save_dir, filename)

        print(f"[INFO] 동영상 다운로드 중...: {url}")
        # 403 Forbidden 방지를 위한 헤더 추가
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Referer': 'https://commons.ssu.ac.kr/',
            'Accept': 'video/webm,video/ogg,video/*;q=0.9,application/ogg;q=0.7,audio/*;q=0.6,*/*;q=0.5',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        response = requests.get(url, stream=True, headers=headers)
        response.raise_for_status()

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        print(f"[SUCCESS] 다운로드 완료: {filepath}")
        return os.path.abspath(filepath)
    except Exception as e:
        print(f"[ERROR] 다운로드 실패: {e}")
        raise e
